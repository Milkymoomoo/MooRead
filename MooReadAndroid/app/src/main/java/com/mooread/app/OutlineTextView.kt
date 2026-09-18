package com.mooread.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import androidx.appcompat.widget.AppCompatTextView

class OutlineTextView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : AppCompatTextView(context, attrs) {
    var strokeColor: Int = Color.BLACK
    var strokeWidthPx: Float = 4f

    override fun onDraw(canvas: Canvas) {
        val p = paint
        val fill = currentTextColor
        p.style = Paint.Style.STROKE
        p.strokeWidth = strokeWidthPx
        setTextColor(strokeColor)
        super.onDraw(canvas)
        p.style = Paint.Style.FILL
        setTextColor(fill)
        super.onDraw(canvas)
    }
}
