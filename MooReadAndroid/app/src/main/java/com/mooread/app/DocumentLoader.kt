package com.mooread.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.nio.charset.Charset
import java.util.zip.ZipInputStream

data class LoadedDoc(
    val title: String,
    val text: String,
    val kind: String,
    val chunks: List<String>
)

object DocumentLoader {
    private val target = 720

    fun load(context: Context, uri: Uri, ocr: OcrHelper, onStatus: ((String) -> Unit)? = null): LoadedDoc {
        val name = nameOf(context, uri)
        val mime = context.contentResolver.getType(uri) ?: ""
        val lower = name.lowercase()
        onStatus?.invoke("Opening $name…")
        val text = when {
            lower.endsWith(".epub") || mime.contains("epub") -> {
                onStatus?.invoke("Unpacking EPUB…")
                loadEpub(context, uri)
            }
            lower.endsWith(".pdf") || mime == "application/pdf" -> {
                onStatus?.invoke("Reading PDF pages / OCR if scanned…")
                loadPdf(context, uri, ocr)
            }
            lower.endsWith(".rtf") || mime.contains("rtf") -> {
                onStatus?.invoke("Stripping RTF…")
                loadRtf(context, uri)
            }
            mime.startsWith("image/") || lower.matches(Regex(".*\\.(png|jpe?g|webp|bmp|gif|tiff?)$")) -> {
                onStatus?.invoke("Running on-device text detection on image…")
                ocr.recognizeUri(context, uri).ifBlank { "[No text detected in image]" }
            }
            else -> {
                onStatus?.invoke("Reading text file…")
                readText(context, uri)
            }
        }
        onStatus?.invoke("Chunking ${text.length} characters for the voice pipeline…")
        val chunks = chunk(text)
        onStatus?.invoke("Ready — ${chunks.size} spoken blocks")
        return LoadedDoc(
            title = name.substringBeforeLast('.'),
            text = text,
            kind = mime.ifBlank { lower.substringAfterLast('.', "text") },
            chunks = chunks
        )
    }

    fun chunk(text: String): List<String> {
        val paras = text.split(Regex("\\n\\s*\\n")).map { it.trim() }.filter { it.isNotEmpty() }
        val out = mutableListOf<String>()
        val buf = StringBuilder()
        for (para in paras) {
            val sentences = para.split(Regex("(?<=[.!?])\\s+"))
            for (s in sentences) {
                if (buf.length > 0 && buf.length + s.length + 1 > target) {
                    out += buf.toString().trim()
                    buf.clear()
                }
                if (buf.isNotEmpty()) buf.append(' ')
                buf.append(s.trim())
            }
            if (buf.length >= target) {
                out += buf.toString().trim()
                buf.clear()
            }
        }
        if (buf.isNotBlank()) out += buf.toString().trim()
        if (out.isEmpty() && text.isNotBlank()) out += text.trim()
        val exploded = mutableListOf<String>()
        for (block in out) {
            if (block.length <= 1400) exploded += block
            else {
                var i = 0
                while (i < block.length) {
                    val end = (i + target).coerceAtMost(block.length)
                    exploded += block.substring(i, end)
                    i = end
                }
            }
        }
        return exploded
    }

    fun fromText(title: String, text: String, kind: String = "camera"): LoadedDoc {
        val body = text.trim()
        return LoadedDoc(title = title, text = body, kind = kind, chunks = chunk(body))
    }

    private fun nameOf(context: Context, uri: Uri): String {
        context.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) return it.getString(0)
        }
        return uri.lastPathSegment ?: "document"
    }

    private fun readText(context: Context, uri: Uri): String {
        context.contentResolver.openInputStream(uri)?.use { raw ->
            val bytes = raw.readBytes()
            return decode(bytes)
        }
        return ""
    }

    private fun decode(bytes: ByteArray): String {
        val charsets = listOf(Charsets.UTF_8, Charset.forName("windows-1252"), Charsets.ISO_8859_1)
        for (cs in charsets) {
            try {
                return String(bytes, cs)
            } catch (_: Exception) {
            }
        }
        return String(bytes, Charsets.UTF_8)
    }

    private fun loadRtf(context: Context, uri: Uri): String {
        val raw = readText(context, uri)
        return raw
            .replace(Regex("\\\\par[d]?"), "\n")
            .replace(Regex("\\\\[a-z]+-?\\d* ?"), "")
            .replace(Regex("[{}]"), "")
            .replace("\\tab", "\t")
            .trim()
    }

    private fun loadEpub(context: Context, uri: Uri): String {
        val parts = mutableListOf<String>()
        context.contentResolver.openInputStream(uri)?.use { input ->
            ZipInputStream(BufferedInputStream(input)).use { zip ->
                var entry = zip.nextEntry
                while (entry != null) {
                    val n = entry.name.lowercase()
                    if (!entry.isDirectory && (n.endsWith(".xhtml") || n.endsWith(".html") || n.endsWith(".htm"))) {
                        val html = zip.readBytes().toString(Charsets.UTF_8)
                        val text = html
                            .replace(Regex("(?is)<script.*?>.*?</script>"), " ")
                            .replace(Regex("(?i)<br\\s*/?>"), "\n")
                            .replace(Regex("(?i)</(p|div|h[1-6]|li)>"), "\n\n")
                            .replace(Regex("<[^>]+>"), " ")
                            .replace(Regex("&nbsp;"), " ")
                            .replace(Regex("&"), "&")
                            .replace(Regex("<"), "<")
                            .replace(Regex(">"), ">")
                            .replace(Regex("[ \\t]+"), " ")
                            .trim()
                        if (text.isNotEmpty()) parts += text
                    }
                    entry = zip.nextEntry
                }
            }
        }
        return parts.joinToString("\n\n")
    }

    private fun loadPdf(context: Context, uri: Uri, ocr: OcrHelper): String {
        val pfd: ParcelFileDescriptor = context.contentResolver.openFileDescriptor(uri, "r") ?: return ""
        val renderer = PdfRenderer(pfd)
        val pages = mutableListOf<String>()
        try {
            for (i in 0 until renderer.pageCount) {
                renderer.openPage(i).use { page ->
                    val bmp = Bitmap.createBitmap(
                        (page.width * 1.5).toInt().coerceAtLeast(1),
                        (page.height * 1.5).toInt().coerceAtLeast(1),
                        Bitmap.Config.ARGB_8888
                    )
                    page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    val text = ocr.recognizeBitmap(bmp)
                    pages += text.ifBlank { "[Page ${i + 1}]" }
                    bmp.recycle()
                }
            }
        } finally {
            renderer.close()
            pfd.close()
        }
        return pages.joinToString("\n\n")
    }
}
