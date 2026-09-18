package com.mooread.app

import android.content.Context
import android.net.Uri
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.io.File

/**
 * Reads the PDF text layer page-by-page. OCR is only for pages with no layer.
 */
class PdfTextSource(context: Context, uri: Uri) {
    private val file: File = File(context.cacheDir, "mooread-open.pdf")
    private val doc: PDDocument
    val pageCount: Int

    init {
        PDFBoxResourceLoader.init(context.applicationContext)
        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "Cannot open PDF" }
            file.outputStream().use { input.copyTo(it) }
        }
        doc = PDDocument.load(file)
        pageCount = doc.numberOfPages
    }

    @Synchronized
    fun pageText(index: Int): String {
        if (index < 0 || index >= pageCount) return ""
        val strip = PDFTextStripper()
        strip.startPage = index + 1
        strip.endPage = index + 1
        strip.sortByPosition = true
        return clean(strip.getText(doc) ?: "")
    }

    fun close() {
        try { doc.close() } catch (_: Exception) {}
    }

    companion object {
        fun clean(raw: String): String {
            var t = raw.replace(Regex("(\\w)-\\s*[\\r\\n]+\\s*(\\w)"), "$1$2")
            t = t.replace(Regex("[ \\t]+"), " ")
            t = t.replace(Regex("\\n{3,}"), "\n\n")
            return t.trim()
        }
    }
}
