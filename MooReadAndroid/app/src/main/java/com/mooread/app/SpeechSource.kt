package com.mooread.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Pulls speakable text just ahead of the voice cursor.
 * PDFs are OCR'd one page at a time; spoken pages are dropped.
 */
class SpeechSource(private val ocr: OcrHelper) {
    var title: String = "document"
        private set
    var kind: String = "text"
        private set
    var pageCount: Int = 1
        private set

    private val chunks = ArrayList<String>()
    private val lock = Any()
    private var renderer: PdfRenderer? = null
    private var pfd: ParcelFileDescriptor? = null
    private var textSrc: PdfTextSource? = null
    private var nextPage = 0
    private val closed = AtomicBoolean(false)
    private val display = StringBuilder()
    @Volatile var eof = false
        private set
    var onGrow: ((String) -> Unit)? = null
    var onStatus: ((String) -> Unit)? = null

    fun openUri(context: Context, uri: Uri, rawText: String?, isPdf: Boolean) {
        close()
        closed.set(false)
        eof = false
        nextPage = 0
        chunks.clear()
        display.clear()
        title = uri.lastPathSegment?.substringAfterLast('/')?.substringBeforeLast('.') ?: "document"
        if (isPdf) {
            kind = "pdf"
            try {
                textSrc = PdfTextSource(context, uri)
                pageCount = textSrc!!.pageCount
            } catch (ex: Exception) {
                onStatus?.invoke("PDF text layer failed (${ex.message}) — will OCR pages")
                textSrc = null
            }
            pfd = context.contentResolver.openFileDescriptor(uri, "r")
            val fd = pfd
            if (fd != null) {
                try { renderer = PdfRenderer(fd) } catch (_: Exception) { renderer = null }
                if (pageCount <= 1) pageCount = renderer?.pageCount ?: pageCount
            }
            if (textSrc == null && renderer == null) {
                eof = true
                return
            }
            ensure(0)
            return
        }
        kind = "text"
        ingestText(rawText ?: "")
        eof = true
        pageCount = 1
    }

    fun openText(title: String, text: String, kind: String) {
        close()
        closed.set(false)
        this.title = title
        this.kind = kind
        ingestText(text)
        eof = true
        pageCount = 1
    }

    fun snapshot(): List<String> = synchronized(lock) { chunks.toList() }

    fun displayText(): String = synchronized(lock) { display.toString() }

    fun knownCount(): Int = synchronized(lock) { chunks.size }

    fun chunkAt(index: Int): String? {
        ensure(index)
        return synchronized(lock) { chunks.getOrNull(index) }
    }

    fun ensure(index: Int) {
        if (index < 0) return
        while (!closed.get()) {
            val have = synchronized(lock) { chunks.size }
            if (have > index) return
            if (eof) return
            if (!pullNextPage()) return
        }
    }

    fun dropBefore(index: Int) {
        // Keep strings for the reader window; only trim very old pages.
        synchronized(lock) {
            if (index < 8) return
            // leave list indices stable so cursor math stays valid
        }
    }

    fun close() {
        closed.set(true)
        try { renderer?.close() } catch (_: Exception) {}
        try { pfd?.close() } catch (_: Exception) {}
        try { textSrc?.close() } catch (_: Exception) {}
        renderer = null
        pfd = null
        textSrc = null
    }

    private fun ingestText(text: String) {
        val pieces = DocumentLoader.chunk(text)
        val keep = pieces.filter { speakable(it) }.ifEmpty { pieces.filter { it.isNotBlank() } }
        synchronized(lock) {
            chunks.clear()
            chunks.addAll(keep)
            display.clear()
            display.append(text)
        }
    }

    private fun pullNextPage(): Boolean {
        val pageIndex: Int
        val total: Int
        synchronized(lock) {
            total = maxOf(pageCount, renderer?.pageCount ?: 0, textSrc?.pageCount ?: 0)
            if (nextPage >= total && total > 0) {
                eof = true
                return false
            }
            if (textSrc == null && renderer == null) {
                eof = true
                return false
            }
            pageIndex = nextPage++
        }
        onStatus?.invoke("Reading page ${pageIndex + 1}/$total…")
        var text = ""
        try {
            text = textSrc?.pageText(pageIndex) ?: ""
        } catch (ex: Exception) {
            onStatus?.invoke("Text layer page ${pageIndex + 1}: ${ex.message}")
        }
        text = PdfTextSource.clean(text)
        if (!speakable(text)) {
            onStatus?.invoke("No text layer on page ${pageIndex + 1} — OCR")
            val pdf = renderer
            text = if (pdf != null) {
                try { renderPage(pdf, pageIndex) } catch (ex: Exception) {
                    onStatus?.invoke("OCR page ${pageIndex + 1} failed: ${ex.message}")
                    ""
                }
            } else ""
            text = PdfTextSource.clean(text)
        }
        val pieces = DocumentLoader.chunk(text).filter { speakable(it) }
        synchronized(lock) {
            if (pieces.isEmpty()) {
                onStatus?.invoke("Page ${pageIndex + 1} had no readable words — skipping")
                return true
            }
            chunks.addAll(pieces)
            if (display.isNotEmpty()) display.append("\n\n")
            display.append(text)
        }
        onGrow?.invoke(synchronized(lock) { display.toString() })
        onStatus?.invoke("Queued ${synchronized(lock) { chunks.size }} spoken blocks (page ${pageIndex + 1}/$total)")
        return true
    }

    private fun renderPage(pdf: PdfRenderer, index: Int): String {
        return try {
            pdf.openPage(index).use { page ->
                val scale = (1400f / maxOf(page.width, 1)).coerceIn(1.4f, 2.5f)
                val w = (page.width * scale).toInt().coerceAtLeast(1)
                val h = (page.height * scale).toInt().coerceAtLeast(1)
                val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                try {
                    page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    ocr.recognizeBitmap(bmp)
                } finally {
                    bmp.recycle()
                }
            }
        } catch (ex: Exception) {
            onStatus?.invoke("PDF page ${index + 1} failed: ${ex.message}")
            ""
        }
    }

    companion object {
        fun speakable(text: String): Boolean {
            val cleaned = text
                .replace(Regex("\\[Page\\s*\\d+\\]", RegexOption.IGNORE_CASE), " ")
                .replace(Regex("(?i)\\bpage\\s+\\d+\\b"), " ")
                .trim()
            val letters = cleaned.count { it.isLetter() }
            val cjk = cleaned.count { ch ->
                val c = ch.code
                (c in 0x3040..0x30FF) || (c in 0x3400..0x9FFF)
            }
            return letters + cjk >= 2
        }
    }
}
