package com.bee.island;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.animation.OvershootInterpolator;
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
    private static final int RIM_OK = 0xFF30D158;
    private static final int RIM_FAIL = 0xFFFF453A;
    private static final int TEXT = 0xFFF5F5F7;

    private String state = STATE_IDLE;
    private String statusText = "";
    /** When false, backdrop draws the capsule; this view only morphs + status text. */
    private boolean drawCapsule = true;

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
    private int anchorLeftPx;
    private int anchorTopPx;
    private int anchorMaxWPx;
    private int anchorMaxHPx;
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

    /**
     * Parent overlay is sized for listen max; idle morph insets so the pill
     * stays centered on the camera punch-hole.
     */
    public void setAnchorInsets(int listenLeftPx, int listenTopPx, int maxWPx, int maxHPx) {
        anchorLeftPx = listenLeftPx;
        anchorTopPx = listenTopPx;
        anchorMaxWPx = maxWPx;
        anchorMaxHPx = maxHPx;
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

    public void setDrawCapsule(boolean draw) {
        drawCapsule = draw;
        setWillNotDraw(false);
        setBackgroundColor(0x00000000);
        invalidate();
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

    private int marginForWidth(int widthPx) {
        if (anchorMaxWPx <= 0) {
            return anchorLeftPx;
        }
        return anchorLeftPx + Math.max(0, (anchorMaxWPx - widthPx) / 2);
    }

    private int marginForHeight(int heightPx) {
        if (anchorMaxHPx <= 0) {
            return anchorTopPx;
        }
        return anchorTopPx + Math.max(0, (anchorMaxHPx - heightPx) / 2);
    }

    private void morphToSize(final int targetWidthPx, final int targetHeightPx) {
        if (targetWidthPx <= 0) {
            return;
        }
        cancelWidthMorph();
        final int fromW = currentWidthPx <= 0 ? targetWidthPx : currentWidthPx;
        final int fromH = currentHeightPx <= 0 ? targetHeightPx : currentHeightPx;
        final int fromLeft;
        final int fromTop;
        if (getLayoutParams() instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams cur = (FrameLayout.LayoutParams) getLayoutParams();
            fromLeft = cur.leftMargin;
            fromTop = cur.topMargin;
        } else {
            fromLeft = marginForWidth(fromW);
            fromTop = marginForHeight(fromH);
        }
        final int toLeft = marginForWidth(targetWidthPx);
        final int toTop = marginForHeight(targetHeightPx);
        if (fromW == targetWidthPx && fromH == targetHeightPx
                && fromLeft == toLeft && fromTop == toTop) {
            currentWidthPx = targetWidthPx;
            currentHeightPx = targetHeightPx;
            return;
        }
        widthAnim = ValueAnimator.ofFloat(0f, 1f);
        widthAnim.setDuration(240);
        widthAnim.setInterpolator(new OvershootInterpolator(1.6f));
        widthAnim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator animation) {
                float t = ((Float) animation.getAnimatedValue()).floatValue();
                int width = Math.round(fromW + (targetWidthPx - fromW) * t);
                int height = Math.round(fromH + (targetHeightPx - fromH) * t);
                int left = Math.round(fromLeft + (toLeft - fromLeft) * t);
                int top = Math.round(fromTop + (toTop - fromTop) * t);
                currentWidthPx = width;
                currentHeightPx = height;
                if (getLayoutParams() instanceof FrameLayout.LayoutParams) {
                    FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) getLayoutParams();
                    lp.width = width;
                    lp.height = height;
                    lp.leftMargin = left;
                    lp.topMargin = top;
                    setLayoutParams(lp);
                } else if (getLayoutParams() != null) {
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
        if (drawCapsule) {
            canvas.drawRoundRect(pillRect, radius, radius, fillPaint);
            canvas.drawRoundRect(pillRect, radius, radius, rimPaint);
        }
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
