package com.bee.island;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;

/**
 * Solid black Dynamic Island pill with muted rim and width morph.
 *
 * <p>States: idle / listening / thinking / success / fail / hidden.
 * Fill is always black; rim is a hairline (never gold).</p>
 */
public class IslandPillView extends FrameLayout {

    public static final String STATE_IDLE = "idle";
    public static final String STATE_LISTENING = "listening";
    public static final String STATE_THINKING = "thinking";
    public static final String STATE_SUCCESS = "success";
    public static final String STATE_FAIL = "fail";
    public static final String STATE_HIDDEN = "hidden";

    private static final int FILL_BLACK = 0xFF000000;
    private static final int RIM_IDLE = 0xFF2C2C2E;
    private static final int RIM_LISTEN = 0x66FFFFFF;
    private static final int RIM_THINK = 0x44FFFFFF;
    private static final int RIM_OK = 0xFF4CAF50;
    private static final int RIM_FAIL = 0xFFD32F2F;
    private static final int TEXT = 0xFFF5F5F7;

    private String state = STATE_IDLE;
    private String statusText = "";

    private final Paint rimPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fillPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint statusPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF pillRect = new RectF();

    private int idleWidthPx;
    private int listenWidthPx;
    private int idleHeightPx;
    private int listenHeightPx;
    private int currentWidthPx;
    private int currentHeightPx;
    private ValueAnimator widthAnim;
    private float density = 1f;

    public IslandPillView(Context context) {
        super(context);
        init(context);
    }

    public IslandPillView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init(context);
    }

    public IslandPillView(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
        init(context);
    }

    private void init(Context context) {
        setWillNotDraw(false);
        try {
            density = context.getResources().getDisplayMetrics().density;
        } catch (Exception ignored) {
            density = 1f;
        }
        idleWidthPx = Math.round(IslandTouch.IDLE_W_DP * density);
        listenWidthPx = Math.round(IslandTouch.LISTEN_W_DP * density);
        idleHeightPx = Math.round(34f * density);
        listenHeightPx = Math.round(38f * density);
        currentWidthPx = idleWidthPx;
        currentHeightPx = idleHeightPx;
        rimPaint.setStyle(Paint.Style.STROKE);
        rimPaint.setStrokeWidth(1.25f * density);
        rimPaint.setColor(RIM_IDLE);
        fillPaint.setStyle(Paint.Style.FILL);
        fillPaint.setColor(FILL_BLACK);
        statusPaint.setColor(TEXT);
        statusPaint.setTextAlign(Paint.Align.CENTER);
        statusPaint.setTextSize(11f * density);
        statusPaint.setFakeBoldText(false);
    }

    public String getState() {
        return state == null ? STATE_IDLE : state;
    }

    public String getStatusText() {
        return statusText == null ? "" : statusText;
    }

    public void setStatusText(String text) {
        statusText = text == null ? "" : text;
        invalidate();
    }

    public void setIdleWidth(int px) {
        idleWidthPx = px;
    }

    public void setListenWidth(int px) {
        listenWidthPx = px;
    }

    public void setState(String next) {
        if (next == null) {
            next = STATE_IDLE;
        }
        state = next;
        if (STATE_HIDDEN.equals(state)) {
            cancelWidthMorph();
            setVisibility(GONE);
            return;
        }
        setVisibility(VISIBLE);
        int targetW = currentWidthPx;
        int targetH = idleHeightPx;
        if (STATE_IDLE.equals(state)) {
            targetW = idleWidthPx;
            targetH = idleHeightPx;
            rimPaint.setColor(RIM_IDLE);
            statusPaint.setColor(TEXT);
        } else if (STATE_LISTENING.equals(state)) {
            targetW = listenWidthPx;
            targetH = listenHeightPx;
            rimPaint.setColor(RIM_LISTEN);
            statusPaint.setColor(TEXT);
            if (statusText == null || statusText.isEmpty()) {
                statusText = "Listening…";
            }
        } else if (STATE_THINKING.equals(state)) {
            targetW = listenWidthPx;
            targetH = listenHeightPx;
            rimPaint.setColor(RIM_THINK);
            statusPaint.setColor(TEXT);
            if (statusText == null || statusText.isEmpty()) {
                statusText = "Thinking…";
            }
        } else if (STATE_SUCCESS.equals(state)) {
            targetW = idleWidthPx;
            targetH = idleHeightPx;
            rimPaint.setColor(RIM_OK);
            statusPaint.setColor(TEXT);
        } else if (STATE_FAIL.equals(state)) {
            targetW = idleWidthPx;
            targetH = idleHeightPx;
            rimPaint.setColor(RIM_FAIL);
            statusPaint.setColor(TEXT);
        }
        morphToSize(targetW, targetH);
        invalidate();
    }

    public void setListening(boolean listening) {
        if (listening) {
            if (!STATE_LISTENING.equals(state)) {
                statusText = "Listening…";
            }
            setState(STATE_LISTENING);
        } else {
            if (STATE_LISTENING.equals(state) || STATE_THINKING.equals(state)) {
                setState(STATE_IDLE);
            }
        }
    }

    public void setThinking() {
        setState(STATE_THINKING);
    }

    public void setSuccess(String status) {
        if (status != null && !status.isEmpty()) {
            statusText = status;
        }
        setState(STATE_SUCCESS);
    }

    public void setFail(String status) {
        if (status != null && !status.isEmpty()) {
            statusText = status;
        }
        setState(STATE_FAIL);
    }

    public void setHidden(boolean hidden) {
        if (hidden) {
            setState(STATE_HIDDEN);
        } else if (STATE_HIDDEN.equals(state)) {
            statusText = "";
            setState(STATE_IDLE);
        }
    }

    private void cancelWidthMorph() {
        if (widthAnim != null) {
            try {
                widthAnim.cancel();
            } catch (Exception ignored) {
            }
            widthAnim = null;
        }
    }

    private void morphToSize(final int targetWidthPx, final int targetHeightPx) {
        if (targetWidthPx <= 0) {
            return;
        }
        cancelWidthMorph();
        final int fromW = currentWidthPx <= 0 ? targetWidthPx : currentWidthPx;
        final int fromH = currentHeightPx <= 0 ? targetHeightPx : currentHeightPx;
        if (fromW == targetWidthPx && fromH == targetHeightPx) {
            currentWidthPx = targetWidthPx;
            currentHeightPx = targetHeightPx;
            return;
        }
        widthAnim = ValueAnimator.ofFloat(0f, 1f);
        widthAnim.setDuration(320);
        widthAnim.setInterpolator(new DecelerateInterpolator(1.6f));
        widthAnim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator animation) {
                float t = ((Float) animation.getAnimatedValue()).floatValue();
                int width = Math.round(fromW + (targetWidthPx - fromW) * t);
                int height = Math.round(fromH + (targetHeightPx - fromH) * t);
                currentWidthPx = width;
                currentHeightPx = height;
                if (getLayoutParams() != null) {
                    getLayoutParams().width = width;
                    getLayoutParams().height = height;
                    requestLayout();
                }
                invalidate();
            }
        });
        widthAnim.start();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (STATE_HIDDEN.equals(state)) {
            return;
        }
        float w = getWidth();
        float h = getHeight();
        if (w <= 0 || h <= 0) {
            return;
        }
        float inset = Math.max(1f, density * 0.75f);
        float radius = h / 2f;
        pillRect.set(inset, inset, w - inset, h - inset);
        canvas.drawRoundRect(pillRect, radius, radius, fillPaint);
        canvas.drawRoundRect(pillRect, radius, radius, rimPaint);
        String line = statusText == null ? "" : statusText.trim();
        if (!line.isEmpty() && (STATE_LISTENING.equals(state)
                || STATE_THINKING.equals(state)
                || STATE_SUCCESS.equals(state)
                || STATE_FAIL.equals(state))) {
            Paint.FontMetrics fm = statusPaint.getFontMetrics();
            float baseline = h / 2f - (fm.ascent + fm.descent) / 2f;
            canvas.drawText(line, w / 2f, baseline, statusPaint);
        }
    }
}
