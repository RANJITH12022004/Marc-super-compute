package com.bee.island;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;

import java.lang.ref.WeakReference;
import java.util.ArrayList;

/** Lean foreground service that hosts the island pill and tap-to-listen. */
public class IslandService extends Service {

    public static final float CAMERA_X_PX = 540;
    public static final float CAMERA_Y_PX = 68.6f;

    public static final String ACTION_LISTEN = "com.bee.island.LISTEN";
    public static final String ACTION_ASK = "com.bee.island.ASK";
    public static final String ACTION_PLAY_WATER = "com.bee.island.PLAY_WATER";

    private static final String CHANNEL_ID = "island";
    private static final int NOTIF_ID = 41;
    private static final long LISTEN_TIMEOUT_MS = 8000;

    private static WeakReference<IslandAccess> host;

    public static void bindHost(IslandAccess svc) {
        host = (svc == null) ? null : new WeakReference<>(svc);
    }

    private static boolean isHostBound() {
        return host != null && host.get() != null;
    }

    private WindowManager wm;
    private View pill;
    private WaterHeroView hero;
    private GestureDetector tap;
    private SpeechRecognizer recognizer;
    private boolean listening;
    private boolean confirming;
    private long listenStartedAt;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Runnable hourlyWater = new Runnable() {
        @Override
        public void run() {
            playWaterNow();
            main.postDelayed(this, WaterHero.HOUR_MS);
        }
    };
    private final Runnable hideHero = new Runnable() {
        @Override
        public void run() {
            hideHero();
        }
    };

    private final Runnable listenWatch = new Runnable() {
        @Override
        public void run() {
            listening = false;
            try {
                if (recognizer != null) {
                    recognizer.cancel();
                }
            } catch (Exception ignored) {
            }
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        ensureForeground();
        ensurePill();
        long last = getSharedPreferences("bee_water", MODE_PRIVATE).getLong("last", 0L);
        long delay = WaterHero.nextDelayMs(last > 0L, last, System.currentTimeMillis());
        main.postDelayed(hourlyWater, delay);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            String action = intent.getAction();
            if (ACTION_LISTEN.equals(action)) {
                startListening();
            } else if (ACTION_ASK.equals(action)) {
                String text = intent.getStringExtra("text");
                if (text != null && !text.trim().isEmpty()) {
                    onHeard(text.trim());
                } else {
                    startListening();
                }
            } else if (ACTION_PLAY_WATER.equals(action)) {
                playWaterNow();
            }
        } else {
            ensurePill();
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        main.removeCallbacks(listenWatch);
        main.removeCallbacks(hourlyWater);
        main.removeCallbacks(hideHero);
        hideHero();
        try {
            if (recognizer != null) {
                recognizer.cancel();
                recognizer.destroy();
            }
        } catch (Exception ignored) {
        }
        recognizer = null;
        try {
            if (wm != null && pill != null) {
                wm.removeView(pill);
            }
        } catch (Exception ignored) {
        }
        pill = null;
        super.onDestroy();
    }

    private void ensureForeground() {
        try {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationChannel ch = new NotificationChannel(
                        CHANNEL_ID, "Island", NotificationManager.IMPORTANCE_MIN);
                nm.createNotificationChannel(ch);
            }
            Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                    ? new Notification.Builder(this, CHANNEL_ID)
                    : new Notification.Builder(this);
            b.setSmallIcon(android.R.drawable.presence_audio_online)
                    .setContentTitle("Bee island")
                    .setContentText("Listening for tap")
                    .setOngoing(true);
            startForeground(NOTIF_ID, b.build());
        } catch (Exception ignored) {
        }
    }

    private void ensurePill() {
        if (pill != null) {
            return;
        }
        try {
            if (wm == null) {
                wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            }
            if (wm == null) {
                return;
            }
            FrameLayout layout = new FrameLayout(this);
            int w = dp(126);
            int h = dp(34);
            layout.setLayoutParams(new FrameLayout.LayoutParams(w, h));
            layout.setBackgroundResource(R.drawable.island_capsule);
            ImageView pips = new ImageView(this);
            pips.setImageResource(R.drawable.island_pips);
            pips.setScaleType(ImageView.ScaleType.CENTER);
            layout.addView(pips, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT));

            tap = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
                @Override
                public boolean onDown(MotionEvent e) {
                    return true;
                }

                @Override
                public boolean onSingleTapUp(MotionEvent e) {
                    long age = listening ? SystemClock.uptimeMillis() - listenStartedAt : 0L;
                    String action = IslandTouch.onTap(listening, confirming, age);
                    if ("cancel".equals(action)) {
                        confirming = false;
                        return true;
                    }
                    if ("ignore".equals(action)) {
                        return true;
                    }
                    startListening();
                    return true;
                }
            });
            layout.setOnTouchListener(new View.OnTouchListener() {
                @Override
                public boolean onTouch(View v, MotionEvent event) {
                    return tap.onTouchEvent(event);
                }
            });

            int type;
            if (isHostBound()) {
                type = WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY;
            } else {
                type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
            }
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    w,
                    h,
                    type,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                lp.layoutInDisplayCutoutMode =
                        WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
            }
            lp.x = Math.max(0, Math.round(CAMERA_X_PX - w / 2f));
            lp.y = Math.max(0, Math.round(CAMERA_Y_PX - h / 2f));

            pill = layout;
            addOverlay(pill, lp);
        } catch (Exception ignored) {
        }
    }

    private void addOverlay(View view, WindowManager.LayoutParams lp) {
        try {
            if (wm == null) {
                wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            }
            if (wm == null || view == null) {
                return;
            }
            try {
                wm.removeView(view);
            } catch (Exception ignored) {
            }
            wm.addView(view, lp);
        } catch (Exception ignored) {
        }
    }

    private void startListening() {
        try {
            boolean overlayOk = Settings.canDrawOverlays(this) || isHostBound();
            boolean micOk = checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                    == PackageManager.PERMISSION_GRANTED;
            if (!overlayOk || !micOk) {
                AskRouter.speak(this, "Can't listen yet");
                return;
            }
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                AskRouter.speak(this, "Can't listen yet");
                return;
            }
            if (recognizer == null) {
                recognizer = SpeechRecognizer.createSpeechRecognizer(this);
                recognizer.setRecognitionListener(new RecognitionListener() {
                    @Override
                    public void onReadyForSpeech(android.os.Bundle params) {
                    }

                    @Override
                    public void onBeginningOfSpeech() {
                    }

                    @Override
                    public void onRmsChanged(float rmsdB) {
                    }

                    @Override
                    public void onBufferReceived(byte[] buffer) {
                    }

                    @Override
                    public void onEndOfSpeech() {
                    }

                    @Override
                    public void onError(int error) {
                        listening = false;
                        main.removeCallbacks(listenWatch);
                    }

                    @Override
                    public void onResults(android.os.Bundle results) {
                        listening = false;
                        main.removeCallbacks(listenWatch);
                        ArrayList<String> heard =
                                results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                        if (heard != null && !heard.isEmpty()) {
                            onHeard(heard.get(0));
                        }
                    }

                    @Override
                    public void onPartialResults(android.os.Bundle partialResults) {
                    }

                    @Override
                    public void onEvent(int eventType, android.os.Bundle params) {
                    }
                });
            } else {
                try {
                    recognizer.cancel();
                } catch (Exception ignored) {
                }
            }
            Intent ri = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            ri.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            main.removeCallbacks(listenWatch);
            listening = true;
            listenStartedAt = SystemClock.uptimeMillis();
            recognizer.startListening(ri);
            main.postDelayed(listenWatch, LISTEN_TIMEOUT_MS);
        } catch (Exception ignored) {
        }
    }

    void playWaterNow() {
        try {
            if (wm == null) {
                wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            }
            if (wm == null) {
                return;
            }
            hideHero();
            WaterHeroView view = new WaterHeroView(this);
            int w = dp(220);
            int h = dp(280);
            int type;
            if (isHostBound()) {
                type = WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY;
            } else {
                type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
            }
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    w,
                    h,
                    type,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                lp.layoutInDisplayCutoutMode =
                        WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
            }
            lp.x = Math.max(0, Math.round(CAMERA_X_PX - w / 2f));
            lp.y = Math.max(0, Math.round(CAMERA_Y_PX + dp(24)));
            try {
                wm.addView(view, lp);
                hero = view;
                view.play();
                getSharedPreferences("bee_water", MODE_PRIVATE)
                        .edit()
                        .putLong("last", System.currentTimeMillis())
                        .apply();
                main.removeCallbacks(hideHero);
                main.postDelayed(hideHero, 8000);
            } catch (Exception ignored) {
                hero = null;
            }
        } catch (Exception ignored) {
        }
    }

    private void hideHero() {
        try {
            if (hero != null) {
                hero.stop();
                if (wm != null) {
                    wm.removeView(hero);
                }
            }
        } catch (Exception ignored) {
        }
        hero = null;
    }

    void ask(String text) {
        onHeard(text);
    }

    private void onHeard(String text) {
        AskRouter.handle(this, text);
    }

    private int dp(int v) {
        float d = getResources().getDisplayMetrics().density;
        return Math.round(v * d);
    }
}
