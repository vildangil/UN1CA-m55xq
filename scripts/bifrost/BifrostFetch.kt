import kotlinx.coroutines.runBlocking
import tk.zwander.common.tools.FusClient
import tk.zwander.common.tools.IFusClient
import tk.zwander.common.tools.Request
import tk.zwander.common.tools.VersionFetch
import tk.zwander.common.tools.extractV4Key
import tk.zwander.common.util.firstDataElementDataByTagName
import tk.zwander.common.util.firstElementByTagName
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec

/**
 * UN1CA M55: full Samsung stock downloader using original Bifrost 2.x FUS.
 * Exact historical build only; no IMEI; no publishing the firmware itself.
 * Download a single encrypted archive to the GitHub runner and decrypt
 * IN PLACE to avoid an additional 8 GiB copy.
 */
fun main() = runBlocking {
    val model = "SM-M556B"
    val region = "INS"
    val desiredPda = "M556BXXS4BYH2"
    val out = File(System.getenv("M55_STOCK_ZIP") ?: "m55-oneui7.zip")
    val history = VersionFetch.parseHistoryInfos(
        VersionFetch.performHistoryRequest(model, region)
    )
    val version = history.firstOrNull { it.swVersion.startsWith("$desiredPda/") }
        ?.swVersion ?: error("Stock One UI 7 exact version absent from Samsung history")
    println("M55_FETCH_VERSION=$version")
    val (_, response) = Request.performBinaryInformRetry(
        fw = version,
        model = model,
        region = region,
        imeiSerial = "",
        includeNonce = false,
        legacy = false,
    )
    val body = response.firstElementByTagName("FUSBody")
    val status = body?.firstElementByTagName("Results")
        ?.firstElementByTagName("Status")?.text()
    val put = body?.firstElementByTagName("Put")
    val fileName = put?.firstDataElementDataByTagName("BINARY_NAME").orEmpty()
    val remotePath = put?.firstDataElementDataByTagName("MODEL_PATH").orEmpty()
    val length = put?.firstDataElementDataByTagName("BINARY_BYTE_SIZE")?.toLongOrNull() ?: 0L
    val served = put?.firstDataElementDataByTagName("BINARY_SW_VERSION").orEmpty()
    val modelType = put?.firstDataElementDataByTagName("DEVICE_MODEL_TYPE")
    check(status in setOf("S00", "200") && served == version &&
          length > 0 && fileName.isNotBlank() && remotePath.isNotBlank()) {
        "Samsung returned wrong build or no binary: status=$status"
    }
    println("M55_FETCH_BINARY_METADATA exact=yes bytes=$length encrypted=yes")
    val key = response.extractV4Key()?.first
        ?: error("Samsung did not provide a Bifrost v4 decryption key")
    check(key.size in listOf(16, 24, 32)) { "Unexpected AES key length" }
    val init = Request.createBinaryInit(
        fileName = fileName, nonce = IFusClient.getNonce(false), fw = served,
        modelType = modelType, region = region, legacy = false
    )
    val result = IFusClient.selectClientAndMakeRequest(
        request = FusClient.Request.BINARY_INIT, data = init
    )
    println("M55_FETCH_BINARY_INIT received=${result.isNotBlank()}")
    val auth = FusClient.getAuthV()
    val headers = FusClient.createHeaders(auth)
    val url = FusClient.getDownloadUrl(remotePath + fileName)
    out.parentFile?.mkdirs()

    val chunkSize = 128L * 1024L * 1024L
    FileOutputStream(out, false).use { sink ->
        var start = 0L
        var segment = 0
        while (start < length) {
            val end = minOf(length - 1, start + chunkSize - 1)
            var done = false
            var lastError = ""
            for (attempt in 1..4) {
                if (done) break
                val conn = URL(url).openConnection() as HttpURLConnection
                try {
                    conn.connectTimeout = 30000
                    conn.readTimeout = 90000
                    conn.instanceFollowRedirects = true
                    conn.setRequestProperty("Range", "bytes=$start-$end")
                    for ((name, value) in headers) conn.setRequestProperty(name, value)
                    val httpCode = conn.responseCode
                    val contentRange = conn.getHeaderField("Content-Range").orEmpty()
                    if (httpCode != 206 || !contentRange.startsWith("bytes $start-")) {
                        error("Bad HTTP range response: $httpCode expected=$start-$end")
                    }
                    // Keep each segment in memory, so an interrupted request
                    // never appends partial data to the output file.
                    val expected = (end - start + 1).toInt()
                    val part = ByteArray(expected)
                    conn.inputStream.use { stream ->
                        var n = 0
                        while (n < expected) {
                            val got = stream.read(part, n, expected - n)
                            if (got < 0) error("Truncated Samsung FUS response at $n/$expected")
                            n += got
                        }
                    }
                    sink.write(part)
                    sink.flush()
                    start += expected
                    segment++
                    if (segment % 8 == 0 || start == length) {
                        println("M55_FETCH_PROGRESS downloaded=$start total=$length percent=${start * 100 / length}")
                    }
                    done = true
                } catch (exc: Exception) {
                    lastError = "${exc.javaClass.simpleName}: ${exc.message?.take(160)}"
                    println("M55_FETCH_RETRY part=$segment attempt=$attempt reason=$lastError")
                    if (attempt < 4) Thread.sleep((attempt * 3000).toLong())
                } finally {
                    conn.disconnect()
                }
            }
            check(done) { "Firmware download failed after retries: $lastError" }
        }
    }
    check(out.length() == length) { "Encrypted ZIP length mismatch" }
    println("M55_FETCH_DOWNLOAD_DONE bytes=${out.length()}")

    // Samsung .enc4 uses AES ECB without padding (Bifrost CryptUtils).
    // All writes happen in the same file to limit temporary runner disk use.
    val cipher = Cipher.getInstance("AES/ECB/NoPadding")
    cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"))
    check(length % 16L == 0L) { "Encrypted stream is not aligned to AES block size" }
    val buf = ByteArray(4 * 1024 * 1024)
    RandomAccessFile(out, "rw").use { raf ->
        var off = 0L
        while (off < length) {
            val n = minOf(buf.size.toLong(), length - off).toInt()
            raf.seek(off)
            raf.readFully(buf, 0, n)
            val decoded = cipher.doFinal(buf, 0, n)
            raf.seek(off)
            raf.write(decoded)
            off += n
            if (off % (1024L * 1024L * 1024L) == 0L || off == length) {
                println("M55_DECRYPT_PROGRESS bytes=$off total=$length")
            }
        }
    }
    RandomAccessFile(out, "r").use { raf ->
        val magic = ByteArray(4)
        raf.readFully(magic)
        check(magic[0] == 0x50.toByte() && magic[1] == 0x4b.toByte() &&
              magic[2] == 0x03.toByte() && magic[3] == 0x04.toByte()) {
            "Decryption failed: no ZIP header"
        }
    }
    println("M55_DOWNLOAD_AND_DECRYPT_OK exact_build=$desiredPda bytes=${out.length()}")
}
