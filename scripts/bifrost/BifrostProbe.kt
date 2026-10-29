import kotlinx.coroutines.runBlocking
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import tk.zwander.common.tools.FusClient
import tk.zwander.common.tools.IFusClient
import tk.zwander.common.tools.Request
import tk.zwander.common.tools.VersionFetch
import tk.zwander.common.util.firstElementByTagName
import tk.zwander.common.util.firstDataElementDataByTagName

/**
 * Headless firmware metadata probe that uses the actual Bifrost 2.x
 * SmartDownload implementation. It can test the first 1 MiB of the exact\n * One UI 7 bundle; it never fetches full firmware during this test.
 */
fun main() = runBlocking {
    val model = "SM-M556B"
    val region = "INS"
    val targets = listOf("M556BXXS4BYH2", "M556BXXS4CYL1")

    val history = VersionFetch.parseHistoryInfos(
        VersionFetch.performHistoryRequest(model, region)
    )
    println("Bifrost SmartHistory items: ${history.size}")
    val latest = history.lastOrNull()?.swVersion

    for (pda in targets + listOfNotNull(latest?.split("/")?.firstOrNull())) {
        val version = history.firstOrNull { it.swVersion.startsWith(pda + "/") }
            ?.swVersion ?: continue
        val (_, response) = Request.performBinaryInformRetry(
            fw = version,
            model = model,
            region = region,
            imeiSerial = "",
            includeNonce = false,
            legacy = false,
        )
        val body = response.firstElementByTagName("FUSBody")
        val reply = body?.firstElementByTagName("Results")
        val status = reply?.firstElementByTagName("Status")?.text()
        val put = body?.firstElementByTagName("Put")
        val binary = put?.firstDataElementDataByTagName("BINARY_NAME") ?: ""
        val bytes = put?.firstDataElementDataByTagName("BINARY_BYTE_SIZE") ?: ""
        val path = put?.firstDataElementDataByTagName("MODEL_PATH") ?: ""
        val served = put?.firstDataElementDataByTagName("BINARY_SW_VERSION") ?: ""
        // Samsung's encrypted archive name doesn't normally contain the PDA!
        // Verify the exact returned version plus metadata, not filename text.
        val exact = (status == "S00" || status == "200") &&
            served == version &&
            binary.isNotBlank() &&
            bytes.toLongOrNull()?.let { it > 0 } == true &&
            path.isNotBlank()
        println("BIFROST_EXACT pda=$pda status=$status exact=$exact")
        if (pda == "M556BXXS4BYH2" && exact) {
            println("BIFROST_DOWNLOAD_TEST_BEGIN pda=$pda")
            try {
                val initXml = Request.createBinaryInit(
                    fileName = binary,
                    nonce = IFusClient.getNonce(legacy = false),
                    fw = served,
                    modelType = put?.firstDataElementDataByTagName("DEVICE_MODEL_TYPE"),
                    region = region,
                    legacy = false,
                )
                val initResponse = IFusClient.selectClientAndMakeRequest(
                    request = FusClient.Request.BINARY_INIT,
                    data = initXml,
                )
                println("BIFROST_BINARY_INIT receivedResponse=${initResponse.isNotBlank()}")
                // SmartDownload headers are session-bound. Bifrost normally
                // gives these to Ketch; reuse them with a bounded HTTP range.
                val auth = FusClient.getAuthV()
                val headers = FusClient.createHeaders(auth)
                val url = FusClient.getDownloadUrl(path + binary)
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.instanceFollowRedirects = true
                connection.connectTimeout = 25000
                connection.readTimeout = 30000
                connection.setRequestProperty("Range", "bytes=0-1048575")
                for ((header, value) in headers) {
                    connection.setRequestProperty(header, value)
                }
                val http = connection.responseCode
                val range = connection.getHeaderField("Content-Range") ?: ""
                var received = 0
                val hasher = MessageDigest.getInstance("SHA-256")
                if (http == 200 || http == 206) {
                    connection.inputStream.use { input ->
                        val chunk = ByteArray(65536)
                        while (received < 1048576) {
                            val n = input.read(chunk, 0, minOf(chunk.size, 1048576 - received))
                            if (n <= 0) break
                            received += n
                            hasher.update(chunk, 0, n)
                        }
                    }
                }
                connection.disconnect()
                val hash = hasher.digest().joinToString("") { "%02x".format(it) }
                println("BIFROST_DOWNLOAD_TEST http=$http received=$received bytes rangePresent=${range.isNotBlank()} sha256=$hash")
                if (http !in 200..299 || received < 1048576) {
                    error("Samsung encrypted archive did not deliver a full 1-MiB sample")
                }
                println("BIFROST_DOWNLOAD_TEST_OK")
            } catch (exc: Exception) {
                println("BIFROST_DOWNLOAD_TEST_FAILED type=${exc.javaClass.simpleName} message=${exc.message?.take(140)}")
                throw exc
            }
        }
        println("BIFROST_METADATA pda=$pda filenamePresent=${binary.isNotBlank()} size=$bytes pathPresent=${path.isNotBlank()} servedVersion=${served.ifBlank { "(none)" }}")
        println("BIFROST_VERSION $version")
    }
}
