import kotlinx.coroutines.runBlocking
import tk.zwander.common.tools.Request
import tk.zwander.common.tools.VersionFetch
import tk.zwander.common.util.firstElementByTagName
import tk.zwander.common.util.firstDataElementDataByTagName

/**
 * Headless firmware metadata probe that uses the actual Bifrost 2.x
 * SmartDownload implementation. It never downloads a firmware archive.
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
        val exact = binary.contains(pda) && bytes.toLongOrNull()?.let { it > 0 } == true && path.isNotBlank()
        println("BIFROST_EXACT pda=$pda status=$status exact=$exact")
        println("BIFROST_METADATA pda=$pda filenamePresent=${binary.isNotBlank()} size=$bytes pathPresent=${path.isNotBlank()} servedVersion=${served.ifBlank { "(none)" }}")
        println("BIFROST_VERSION $version")
    }
}
