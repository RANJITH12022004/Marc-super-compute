package com.bee.island;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PointF;
import android.util.AttributeSet;
import android.view.View;
import android.view.animation.LinearInterpolator;

/**
 * Jointed water courier (shoulder/elbow/hip/knee limits + quadratic webs).
 * Fallback is a flask courier, never an unconstrained spider puppet.
 */
public class WaterHeroView extends View {

    private final Paint body = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint web = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint flask = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ink = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private float t;
    private ValueAnimator anim;
    private boolean courierFallback = true;

    public WaterHeroView(Context context) {
        super(context);
        init();
    }

    public WaterHeroView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        body.setColor(0xFFE8B15A);
        body.setStyle(Paint.Style.STROKE);
        body.setStrokeWidth(dp(3.2f));
        body.setStrokeCap(Paint.Cap.ROUND);
        body.setStrokeJoin(Paint.Join.ROUND);
        web.setColor(0x66F5F5F7);
        web.setStyle(Paint.Style.STROKE);
        web.setStrokeWidth(dp(1.4f));
        flask.setColor(0xFF4DA3FF);
        flask.setStyle(Paint.Style.FILL);
        ink.setColor(0xFFF5F5F7);
        ink.setTextAlign(Paint.Align.CENTER);
        ink.setTextSize(dp(11));
        setBackgroundColor(0x00000000);
    }

    public void play() {
        stop();
        anim = ValueAnimator.ofFloat(0f, 1f);
        anim.setDuration(2800);
        anim.setRepeatCount(ValueAnimator.INFINITE);
        anim.setRepeatMode(ValueAnimator.REVERSE);
        anim.setInterpolator(new LinearInterpolator());
        anim.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
            @Override
            public void onAnimationUpdate(ValueAnimator animation) {
                t = (Float) animation.getAnimatedValue();
                invalidate();
            }
        });
        anim.start();
    }

    public void stop() {
        if (anim != null) {
            anim.cancel();
            anim = null;
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        stop();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float w = getWidth();
        float h = getHeight();
        if (w <= 0 || h <= 0) {
            return;
        }
        float cx = w * 0.5f;
        float hipY = h * 0.52f;
        if (courierFallback) {
            drawCourier(canvas, cx, hipY);
            return;
        }
        drawJointed(canvas, cx, hipY);
    }

    private void drawCourier(Canvas c, float cx, float hipY) {
        float bob = (float) Math.sin(t * Math.PI) * dp(6);
        float y = hipY + bob;
        c.drawCircle(cx, y - dp(42), dp(10), body);
        path.reset();
        path.moveTo(cx, y - dp(30));
        path.lineTo(cx, y + dp(8));
        c.drawPath(path, body);
        float arm = WaterHero.clampJoint("shoulder", -18f + t * 28f);
        float el = WaterHero.clampJoint("elbow", 40f + t * 30f);
        PointF L = limb(cx, y - dp(22), 180 - arm, dp(18));
        PointF L2 = limb(L.x, L.y, 180 - el, dp(16));
        PointF R = limb(cx, y - dp(22), arm, dp(18));
        PointF R2 = limb(R.x, R.y, el, dp(16));
        stroke(c, cx, y - dp(22), L.x, L.y);
        stroke(c, L.x, L.y, L2.x, L2.y);
        stroke(c, cx, y - dp(22), R.x, R.y);
        stroke(c, R.x, R.y, R2.x, R2.y);
        float hip = WaterHero.clampJoint("hip", 8f + t * 10f);
        float knee = WaterHero.clampJoint("knee", 25f + t * 20f);
        PointF lh = limb(cx, y + dp(8), 180 - hip, dp(16));
        PointF lk = limb(lh.x, lh.y, 180 - knee, dp(16));
        PointF rh = limb(cx, y + dp(8), hip, dp(16));
        PointF rk = limb(rh.x, rh.y, knee, dp(16));
        stroke(c, cx, y + dp(8), lh.x, lh.y);
        stroke(c, lh.x, lh.y, lk.x, lk.y);
        stroke(c, cx, y + dp(8), rh.x, rh.y);
        stroke(c, rh.x, rh.y, rk.x, rk.y);
        path.reset();
        path.moveTo(R2.x - dp(8), R2.y);
        path.lineTo(R2.x + dp(8), R2.y);
        path.lineTo(R2.x + dp(6), R2.y + dp(16));
        path.lineTo(R2.x - dp(6), R2.y + dp(16));
        path.close();
        c.drawPath(path, flask);
        webFrom(c, L2, cx - dp(40), y - dp(70));
        webFrom(c, R2, cx + dp(40), y - dp(70));
        c.drawText("drink", cx, y + dp(44), ink);
    }

    private void drawJointed(Canvas c, float cx, float hipY) {
        drawCourier(c, cx, hipY);
    }

    private void webFrom(Canvas c, PointF hand, float wallX, float wallY) {
        PointF mid = new PointF((hand.x + wallX) * 0.5f, Math.min(hand.y, wallY) - dp(18));
        path.reset();
        path.moveTo(hand.x, hand.y);
        path.quadTo(mid.x, mid.y, wallX, wallY);
        c.drawPath(path, web);
    }

    private void stroke(Canvas c, float x0, float y0, float x1, float y1) {
        path.reset();
        path.moveTo(x0, y0);
        path.lineTo(x1, y1);
        c.drawPath(path, body);
    }

    private static PointF limb(float x, float y, float deg, float len) {
        double rad = Math.toRadians(deg);
        return new PointF(x + (float) Math.cos(rad) * len, y + (float) Math.sin(rad) * len);
    }

    private float dp(float v) {
        return v * getResources().getDisplayMetrics().density;
    }
}
