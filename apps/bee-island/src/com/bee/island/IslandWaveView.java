package com.bee.island;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.util.AttributeSet;
import android.view.View;

/**
 * Mini 5-bar waveform for listen/think (API from mark-laptop IslandWaveView;
 * source reconstructed — original .java missing, class in bee-debug.apk).
 */
public final class IslandWaveView extends View {
    private static final int BARS = 5;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private boolean active;
    private boolean thinking;
    private float level;
    private float phase;

    public IslandWaveView(Context context) {
        this(context, null);
    }

    public IslandWaveView(Context context, AttributeSet attrs) {
        super(context, attrs);
        paint.setColor(0xFFFFFFFF);
        paint.setStyle(Paint.Style.FILL);
        setVisibility(GONE);
    }

    public void setMode(boolean active, boolean thinking) {
        this.active = active;
        this.thinking = thinking;
        if (!active) {
            level = 0f;
            setVisibility(GONE);
            return;
        }
        setVisibility(VISIBLE);
        invalidate();
        if (thinking) {
            postInvalidateDelayed(36);
        }
    }

    public void setLevel(float next) {
        float clamped = Math.max(0f, Math.min(1f, next));
        level = level * 0.55f + clamped * 0.45f;
        phase += 0.18f + level * 0.22f;
        if (active) {
            invalidate();
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        if (!active) {
            return;
        }
        int w = getWidth();
        int h = getHeight();
        if (w <= 0 || h <= 0) {
            return;
        }
        float d = getResources().getDisplayMetrics().density;
        float barW = Math.max(2f * d, w / (BARS * 2.2f));
        float gap = barW * 0.7f;
        float total = BARS * barW + (BARS - 1) * gap;
        float startX = (w - total) / 2f;
        float midY = h / 2f;
        float maxH = h * 0.85f;
        for (int i = 0; i < BARS; i++) {
            float wave;
            if (thinking) {
                wave = 0.35f + 0.25f * (float) Math.sin(phase + i * 0.9f);
            } else {
                wave = 0.2f + level * (0.45f + 0.35f * (float) Math.sin(phase + i * 1.1f));
            }
            float barH = Math.max(3f * d, maxH * Math.max(0.12f, Math.min(1f, wave)));
            float x = startX + i * (barW + gap);
            float top = midY - barH / 2f;
            canvas.drawRoundRect(x, top, x + barW, top + barH, barW / 2f, barW / 2f, paint);
        }
        if (thinking && active) {
            phase += 0.32f;
            postInvalidateDelayed(36);
        }
    }
}
