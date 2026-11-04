package com.bee.island;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.pm.ServiceInfo;
import android.util.Log;
import android.graphics.PixelFormat;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.graphics.Color;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.OvershootInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
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
    private static final long LISTEN_TIMEOUT_MS = 20000;

    private static final int PILL_W_DP = 126;
    private static final int PILL_H_DP = 34;
    /** Overlay is always sized for listen so morph never clips status icons. */
    private static final int PILL_LISTEN_W_DP = 168;
    private static final int PILL_LISTEN_H_DP = 38;
    private static final long HOLD_MS = 2000;
    private static final long REEL_CAP_MS = 15000;
    private static final long REEL_HEARTBEAT_MS = 300;
    private static final long REEL_COOLDOWN_MS = 1200;

    private static WeakReference<IslandAccess> host;
    private static WeakReference<IslandService> instanceRef;

    static IslandService current() {
        return (instanceRef == null) ? null : instanceRef.get();
    }

    public static void bindHost(IslandAccess svc) {
        host = (svc == null) ? null : new WeakReference<IslandAccess>(svc);
        requestPill(svc);
    }

    static void requestPill(IslandAccess access) {
        if (access != null) {
            host = new WeakReference<IslandAccess>(access);
        }
        IslandService s = (instanceRef == null) ? null : instanceRef.get();
        if (s != null) {
            final IslandService svcRef = s;
            svcRef.main.post(new Runnable() {
                @Override
                public void run() {
                    try {
                        svcRef.ensurePill();
                    } catch (Exception ignored) {
                    }
                }
            });
        }
    }

    public static void onPaymentHidden(final boolean hidden) {
        final IslandService s = (instanceRef == null) ? null : instanceRef.get();
        if (s == null) {
            return;
        }
        s.main.post(new Runnable() {
            @Override
            public void run() {
                try {
                    if (hidden) {
                        s.stopListeningQuiet();
                        s.hideHero();
                        if (s.pillView != null) {
                            s.pillView.setState(IslandPillView.STATE_HIDDEN);
                        } else {
                            s.hidePill();
                        }
                    } else {
                        s.ensurePill();
                    }
                } catch (Exception ignored) {
                }
            }
        });
    }

    private static boolean isHostBound() {
        return host != null && host.get() != null;
    }

    private WindowManager wm;
    private View pill;
    private IslandPillView pillView;
    private IslandBackdropView backdropView;
    private IslandWaveView waveView;
    private TextView lineView;
    private FrameLayout capsule;
    private HydrationHeroView hero;
    private View heroHit;
    private SpeechRecognizer recognizer;
    private MediaRecorder recorder;
    private File recordFile;
    private boolean listening;
    private boolean confirming;
    private boolean museAttempted;
    private boolean srRetryUsed;
    private boolean listenStarting;
    private boolean readyForSpeech;
    private boolean confirmListenArmed;
    private int listenGen;
    private int failSpokenGen = -1;
    private static final String TAG = "BeeIsland";
    private long listenStartedAt;
    private final Handler main = new Handler(Looper.getMainLooper());
    private boolean autoScrolling;
    private long reelStartedAt;
    private float lastReelProgress = -1f;
    private long reelCooldownUntil;
    private final Runnable autoScrollTask = new Runnable() {
        @Override
        public void run() {
            if (!autoScrolling) {
                return;
            }
            long now = SystemClock.uptimeMillis();
            if (now < reelCooldownUntil) {
                main.postDelayed(this, REEL_HEARTBEAT_MS);
                return;
            }
            float progress = -1f;
            try {
                progress = IslandAccess.reelProgress();
            } catch (Exception ignored) {
                progress = -1f;
            }
            boolean finished = progress >= 0.95f
                    || (lastReelProgress >= 0.7f && progress >= 0f && progress <= 0.08f);
            boolean capped = (now - reelStartedAt) >= REEL_CAP_MS;
            if (finished || capped) {
                try {
                    IslandAccess.swipe("up");
                } catch (Exception ignored) {
                }
                reelCooldownUntil = now + REEL_COOLDOWN_MS;
                reelStartedAt = now;
                lastReelProgress = -1f;
            } else if (progress >= 0f) {
                lastReelProgress = progress;
            }
            main.postDelayed(this, REEL_HEARTBEAT_MS);
        }
    };

    public static void startAutoScroll() {
        IslandService s = instanceRef == null ? null : instanceRef.get();
        if (s == null) {
            return;
        }
        s.main.post(new Runnable() {
            @Override
            public void run() {
                s.autoScrolling = true;
                s.reelStartedAt = SystemClock.uptimeMillis();
                s.lastReelProgress = -1f;
                s.reelCooldownUntil = s.reelStartedAt + 500;
                s.main.removeCallbacks(s.autoScrollTask);
                s.main.postDelayed(s.autoScrollTask, REEL_HEARTBEAT_MS);
            }
        });
    }

    public static void stopAutoScroll() {
        IslandService s = instanceRef == null ? null : instanceRef.get();
        if (s == null) {
            return;
        }
        s.main.post(new Runnable() {
            @Override
            public void run() {
                s.autoScrolling = false;
                s.main.removeCallbacks(s.autoScrollTask);
            }
        });
    }
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
            final int gen = listenGen;
            if (recorder != null) {
                finishRecordAndTranscribe();
                return;
            }
            if (!listening || gen != listenGen) {
                return;
            }
            try {
                if (recognizer != null) {
                    recognizer.stopListening();
                }
            } catch (Exception ignored) {
                try {
                    if (recognizer != null) {
                        recognizer.cancel();
                    }
                } catch (Exception ignored2) {
                }
            }
            // Results may still arrive; only fail if this session is still live.
            main.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (listening && gen == listenGen) {
                        listening = false;
                        speakListenFail(gen);
                    }
                }
            }, 400);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        instanceRef = new WeakReference<IslandService>(this);
        ensureForeground();
        ensurePill();
        long last = getSharedPreferences("bee_water", MODE_PRIVATE).getLong("last", 0L);
        long delay = WaterHero.nextDelayMs(last > 0L, last, System.currentTimeMillis());
        main.postDelayed(hourlyWater, delay);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        ensureForeground();
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
        IslandService cur = (instanceRef == null) ? null : instanceRef.get();
        if (cur == this) {
            instanceRef = null;
        }
        autoScrolling = false;
        main.removeCallbacks(autoScrollTask);
        main.removeCallbacks(listenWatch);
        main.removeCallbacks(hourlyWater);
        main.removeCallbacks(hideHero);
        stopRecorder(false);
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
            if (wm != null && pill != null && !isHostBound()) {
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
            Notification notif = b.build();
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            } else {
                startForeground(NOTIF_ID, notif);
            }
        } catch (Exception e) {
            Log.e(TAG, "ensureForeground", e);
            try {
                Notification.Builder b2 = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                        ? new Notification.Builder(this, CHANNEL_ID)
                        : new Notification.Builder(this);
                b2.setSmallIcon(android.R.drawable.presence_audio_online)
                        .setContentTitle("Bee island")
                        .setContentText("Listening for tap")
                        .setOngoing(true);
                startForeground(NOTIF_ID, b2.build());
            } catch (Exception ignored) {
            }
        }
    }

    private void ensurePill() {
        try {
            if (PaymentGate.isHidden()) {
                return;
            }
            if (wm == null) {
                wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            }
            if (wm == null) {
                return;
            }
            // Only remove the service-owned view. When the accessibility host
            // is bound, Access owns the pill view, so never removeView it here.
            if (!isHostBound()) {
                try {
                    if (pill != null) {
                        wm.removeView(pill);
                    }
                } catch (Exception ignored) {
                }
            }
            pill = null;
            pillView = null;
            backdropView = null;
            waveView = null;
            lineView = null;
            capsule = null;

            // Size window for listen morph so growth stays camera-centered
            // and never clips under the battery / network icons.
            int maxW = dp(PILL_LISTEN_W_DP);
            int maxH = dp(PILL_LISTEN_H_DP);
            int idleW = dp(PILL_W_DP);
            int idleH = dp(PILL_H_DP);
            int slopPx = dp(IslandTouch.HIT_SLOP_DP);
            float[] box = IslandTouch.pillWindow(CAMERA_X_PX, CAMERA_Y_PX,
                    (float) maxW, (float) maxH, (float) slopPx);
            int hitW = Math.round(box[2]);
            int hitH = Math.round(box[3]);
            int winX = Math.round(box[0]);
            int winY = Math.round(box[1]);
            int listenLeft = Math.round(box[4]);
            int listenTop = Math.round(box[5]);
            // Idle is inset so its center matches listen (and camera).
            int idleLeft = listenLeft + (maxW - idleW) / 2;
            int idleTop = listenTop + (maxH - idleH) / 2;

            FrameLayout outer = new FrameLayout(this);
            outer.setClipChildren(false);
            outer.setClipToPadding(false);
            outer.setLayoutParams(new FrameLayout.LayoutParams(hitW, hitH));

            // Capsule host = visual band only (not the tall hit/slop box).
            // Mission/speech/wave MUST live here or they render below the island.
            FrameLayout cap = new FrameLayout(this);
            cap.setClipChildren(false);
            FrameLayout.LayoutParams capLp = new FrameLayout.LayoutParams(maxW, maxH);
            capLp.gravity = Gravity.TOP | Gravity.START;
            capLp.leftMargin = listenLeft;
            capLp.topMargin = listenTop;
            cap.setLayoutParams(capLp);
            outer.addView(cap);
            capsule = cap;

            IslandBackdropView backdrop = new IslandBackdropView(this);
            cap.addView(backdrop, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT));
            backdropView = backdrop;

            IslandPillView visual = new IslandPillView(this);
            visual.setAnchorInsets(0, 0, maxW, maxH);
            FrameLayout.LayoutParams visualLp =
                    new FrameLayout.LayoutParams(
                            listening ? maxW : idleW,
                            listening ? maxH : idleH);
            visualLp.gravity = Gravity.CENTER;
            visual.setLayoutParams(visualLp);
            visual.setDrawCapsule(false);
            if (listening) {
                visual.setStatusText("");
                visual.setState(IslandPillView.STATE_LISTENING);
            } else {
                visual.setState(IslandPillView.STATE_IDLE);
            }
            cap.addView(visual);
            pillView = visual;

            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(14), 0, dp(12), 0);
            FrameLayout.LayoutParams rowLp = new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT);
            cap.addView(row, rowLp);

            IslandWaveView wave = new IslandWaveView(this);
            LinearLayout.LayoutParams waveLp = new LinearLayout.LayoutParams(dp(28), dp(18));
            waveLp.rightMargin = dp(4);
            row.addView(wave, waveLp);
            waveView = wave;

            TextView line = new TextView(this);
            line.setTextColor(Color.WHITE);
            line.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f);
            line.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            line.setSingleLine(true);
            line.setEllipsize(android.text.TextUtils.TruncateAt.END);
            line.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            line.setMaxLines(1);
            LinearLayout.LayoutParams lineLp = new LinearLayout.LayoutParams(
                    0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            row.addView(line, lineLp);
            lineView = line;
            if (listening) {
                setIslandLine(BeeAsk.lineFor("listen"));
                setIslandPhase(IslandBackdropView.STATE_LISTENING, true, false);
            } else {
                setIslandLine("");
                setIslandPhase(IslandBackdropView.STATE_IDLE, false, false);
            }

            final boolean[] holdFired = new boolean[1];
            final Runnable[] holdRef = new Runnable[1];
            Runnable holdTask = new Runnable() {
                @Override
                public void run() {
                    holdFired[0] = true;
                    if (confirming) {
                        confirming = false;
                        AskRouter.handle(IslandService.this, "cancel");
                        return;
                    }
                    openApp();
                }
            };
            holdRef[0] = holdTask;
            outer.setOnTouchListener(new View.OnTouchListener() {
                @Override
                public boolean onTouch(View v, MotionEvent event) {
                    int action = event.getActionMasked();
                    if (action == MotionEvent.ACTION_DOWN) {
                        holdFired[0] = false;
                        main.removeCallbacks(holdRef[0]);
                        main.postDelayed(holdRef[0], HOLD_MS);
                        try {
                            v.animate().scaleX(0.93f).scaleY(0.93f)
                                    .setDuration(80).start();
                        } catch (Exception ignored) {
                        }
                        return true;
                    } else if (action == MotionEvent.ACTION_CANCEL) {
                        main.removeCallbacks(holdRef[0]);
                        try {
                            v.animate().scaleX(1f).scaleY(1f).setDuration(180)
                                    .setInterpolator(new OvershootInterpolator(2.2f))
                                    .start();
                        } catch (Exception ignored) {
                        }
                        return true;
                    } else if (action == MotionEvent.ACTION_UP) {
                        try {
                            v.animate().scaleX(1f).scaleY(1f).setDuration(180)
                                    .setInterpolator(new OvershootInterpolator(2.2f))
                                    .start();
                        } catch (Exception ignored) {
                        }
                        stopAutoScroll();
                        if (holdFired[0]) {
                            holdFired[0] = false;
                            return true;
                        }
                        main.removeCallbacks(holdRef[0]);
                        long age = listening
                                ? SystemClock.uptimeMillis() - listenStartedAt : 0L;
                        String tapAction = IslandTouch.onTap(listening, confirming, age);
                        if ("confirm".equals(tapAction)) {
                            confirming = false;
                            AskRouter.handle(IslandService.this, "yes");
                            return true;
                        }
                        if ("cancel".equals(tapAction)) {
                            confirming = false;
                            AskRouter.handle(IslandService.this, "cancel");
                            return true;
                        }
                        if ("ignore".equals(tapAction)) {
                            return true;
                        }
                        startListening();
                        return true;
                    } else if (action == MotionEvent.ACTION_CANCEL) {
                        main.removeCallbacks(holdRef[0]);
                        holdFired[0] = false;
                        return true;
                    }
                    return true;
                }
            });

            int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                    | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                    | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL;
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    hitW,
                    hitH,
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    flags,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                lp.layoutInDisplayCutoutMode =
                        WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
            }
            lp.x = winX;
            lp.y = winY;
            outer.setTag(new int[]{lp.x, lp.y, hitW, hitH});

            if (isHostBound()) {
                IslandAccess h = host.get();
                if (h != null) {
                    h.showPill(outer);
                }
                pill = outer;
                return;
            }

            pill = outer;
            try {
                wm.addView(pill, lp);
            } catch (Exception e) {
                AskRouter.speak(this, "Turn on bee in Accessibility");
            }
        } catch (Exception ignored) {
        }
    }

    private void openApp() {
        try {
            Intent i = new Intent(this, IslandActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(i);
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
            // Free mic from TTS before opening recognizer.
            try {
                AskRouter.stopTts();
            } catch (Exception ignored) {
            }
            main.removeCallbacks(listenWatch);
            stopRecorder(false);
            // Destroy prior recognizer — stop/cancel races fire stale onError and
            // this device's default SR is Google TTS (not Voice Search).
            destroyRecognizer();
            listenGen++;
            listenStarting = true;
            readyForSpeech = false;
            museAttempted = false;
            srRetryUsed = false;
            listening = true;
            listenStartedAt = SystemClock.uptimeMillis();
            if (pillView != null) {
                pillView.setStatusText("");
                pillView.setState(IslandPillView.STATE_LISTENING);
            }
            setIslandLine(BeeAsk.lineFor("listen"));
            setIslandPhase(IslandBackdropView.STATE_LISTENING, true, false);
            // SpeechRecognizer first; Muse/MediaRecorder only if SR unavailable
            // or hard-fails before onReadyForSpeech.
            if (SpeechRecognizer.isRecognitionAvailable(this)) {
                startSpeechFallback();
                return;
            }
            String key = KeyVault.loadKey(this);
            if (key != null && !key.isEmpty() && startRecorder()) {
                listenStarting = false;
                main.postDelayed(listenWatch, LISTEN_TIMEOUT_MS);
                return;
            }
            startSpeechFallback();
        } catch (Exception ignored) {
            listenStarting = false;
        }
    }

    private boolean startRecorder() {
        try {
            stopRecorder(false);
            recordFile = new File(getCacheDir(), "bee-listen.m4a");
            MediaRecorder rec = new MediaRecorder();
            rec.setAudioSource(MediaRecorder.AudioSource.MIC);
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            rec.setOutputFile(recordFile.getAbsolutePath());
            rec.setMaxDuration((int) LISTEN_TIMEOUT_MS);
            rec.prepare();
            rec.start();
            recorder = rec;
            return true;
        } catch (Exception e) {
            stopRecorder(false);
            return false;
        }
    }

    private void stopRecorder(boolean keepFile) {
        MediaRecorder rec = recorder;
        recorder = null;
        if (rec != null) {
            try {
                rec.stop();
            } catch (Exception ignored) {
            }
            try {
                rec.reset();
            } catch (Exception ignored) {
            }
            try {
                rec.release();
            } catch (Exception ignored) {
            }
        }
        if (!keepFile && recordFile != null) {
            try {
                recordFile.delete();
            } catch (Exception ignored) {
            }
            recordFile = null;
        }
    }

    private void finishRecordAndTranscribe() {
        File file = recordFile;
        stopRecorder(true);
        listening = false;
        final String key = KeyVault.loadKey(this);
        final byte[] bytes = readFile(file);
        if (file != null) {
            try {
                file.delete();
            } catch (Exception ignored) {
            }
        }
        recordFile = null;
        if (key == null || key.isEmpty() || bytes == null || bytes.length == 0) {
            startSpeechFallback();
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                String text = "";
                try {
                    text = MuseClient.transcribe(key, bytes, "m4a");
                } catch (Exception ignored) {
                    text = "";
                }
                final String heard = text == null ? "" : text.trim();
                main.post(new Runnable() {
                    @Override
                    public void run() {
                        if (!heard.isEmpty()) {
                            onHeard(heard);
                        } else {
                            startSpeechFallback();
                        }
                    }
                });
            }
        }, "bee-stt").start();
    }

    private static byte[] readFile(File file) {
        if (file == null || !file.isFile()) {
            return new byte[0];
        }
        FileInputStream in = null;
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        try {
            in = new FileInputStream(file);
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) != -1) {
                bos.write(buf, 0, n);
            }
            return bos.toByteArray();
        } catch (Exception e) {
            return new byte[0];
        } finally {
            if (in != null) {
                try {
                    in.close();
                } catch (Exception ignored) {
                }
            }
        }
    }

    /** Prefer Google Voice Search — never the default TTS RecognitionService. */
    private SpeechRecognizer createVoiceRecognizer() {
        ComponentName google = new ComponentName(
                "com.google.android.googlequicksearchbox",
                "com.google.android.voicesearch.serviceapi.GoogleRecognitionService");
        try {
            if (Build.VERSION.SDK_INT >= 31) {
                return SpeechRecognizer.createSpeechRecognizer(this, google);
            }
        } catch (Exception e) {
            Log.w(TAG, "GoogleRecognitionService create failed", e);
        }
        try {
            Intent probe = new Intent(RecognitionServiceIntent());
            ResolveInfo best = null;
            java.util.List<ResolveInfo> list =
                    getPackageManager().queryIntentServices(probe, 0);
            if (list != null) {
                for (int i = 0; i < list.size(); i++) {
                    ResolveInfo ri = list.get(i);
                    if (ri == null || ri.serviceInfo == null) {
                        continue;
                    }
                    String pkg = ri.serviceInfo.packageName == null
                            ? "" : ri.serviceInfo.packageName;
                    String cls = ri.serviceInfo.name == null ? "" : ri.serviceInfo.name;
                    if (pkg.contains("googlequicksearchbox")
                            && cls.toLowerCase(java.util.Locale.US).contains("recognition")) {
                        best = ri;
                        break;
                    }
                    if (best == null && !pkg.contains("tts")
                            && cls.toLowerCase(java.util.Locale.US).contains("recognition")) {
                        best = ri;
                    }
                }
            }
            if (best != null && best.serviceInfo != null && Build.VERSION.SDK_INT >= 31) {
                ComponentName cn = new ComponentName(
                        best.serviceInfo.packageName, best.serviceInfo.name);
                Log.i(TAG, "Using RecognitionService " + cn.flattenToShortString());
                return SpeechRecognizer.createSpeechRecognizer(this, cn);
            }
        } catch (Exception e) {
            Log.w(TAG, "query RecognitionService failed", e);
        }
        Log.w(TAG, "Falling back to default SpeechRecognizer (may be TTS)");
        return SpeechRecognizer.createSpeechRecognizer(this);
    }

    private static Intent RecognitionServiceIntent() {
        return new Intent("android.speech.RecognitionService");
    }

    private void destroyRecognizer() {
        SpeechRecognizer r = recognizer;
        recognizer = null;
        if (r == null) {
            return;
        }
        try {
            r.setRecognitionListener(null);
        } catch (Exception ignored) {
        }
        try {
            r.cancel();
        } catch (Exception ignored) {
        }
        try {
            r.destroy();
        } catch (Exception ignored) {
        }
    }

    private void startSpeechFallback() {
        final int gen = listenGen;
        try {
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                tryMuseRecorderOrFail();
                return;
            }
            if (recognizer == null) {
                recognizer = createVoiceRecognizer();
            }
            if (recognizer == null) {
                tryMuseRecorderOrFail();
                return;
            }
            // Rebind every session so callbacks close over this listenGen.
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override
                public void onReadyForSpeech(android.os.Bundle params) {
                    if (gen != listenGen) {
                        return;
                    }
                    listenStarting = false;
                    readyForSpeech = true;
                }

                @Override
                public void onBeginningOfSpeech() {
                    if (gen != listenGen) {
                        return;
                    }
                    listenStarting = false;
                    readyForSpeech = true;
                }

                @Override
                public void onRmsChanged(float rmsdB) {
                    if (gen != listenGen) {
                        return;
                    }
                    float norm = 0f;
                    try {
                        norm = Math.max(0f, Math.min(1f, (rmsdB + 2f) / 12f));
                    } catch (Exception ignored) {
                        norm = 0f;
                    }
                    final float level = norm;
                    main.post(new Runnable() {
                        @Override
                        public void run() {
                            if (backdropView != null) {
                                backdropView.setVoiceLevel(level);
                            }
                            if (waveView != null) {
                                waveView.setLevel(level);
                            }
                        }
                    });
                }

                @Override
                public void onBufferReceived(byte[] buffer) {
                }

                @Override
                public void onEndOfSpeech() {
                }

                @Override
                public void onError(int error) {
                    if (gen != listenGen) {
                        return;
                    }
                    // Cancel/restart noise while starting a new session.
                    if (listenStarting
                            && (error == SpeechRecognizer.ERROR_CLIENT
                            || error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY)) {
                        return;
                    }
                    main.removeCallbacks(listenWatch);
                    listenStarting = false;
                    Log.w(TAG, "SR onError code=" + error + " ready=" + readyForSpeech);
                    // Pre-ready: one SR retry (new gen so stale errors die), then Muse.
                    if (!readyForSpeech) {
                        if (!srRetryUsed) {
                            scheduleRecognizerRetry(gen, 250);
                            return;
                        }
                        if (!museAttempted) {
                            tryMuseRecorderOrFail();
                            return;
                        }
                        listening = false;
                        speakListenFail(gen);
                        return;
                    }
                    // Post-ready no-match: one quiet restart.
                    if ((error == SpeechRecognizer.ERROR_NO_MATCH
                            || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT)
                            && !srRetryUsed) {
                        scheduleRecognizerRetry(gen, 200);
                        return;
                    }
                    listening = false;
                    speakListenFail(gen);
                }

                @Override
                public void onResults(android.os.Bundle results) {
                    if (gen != listenGen) {
                        return;
                    }
                    listening = false;
                    listenStarting = false;
                    main.removeCallbacks(listenWatch);
                    ArrayList<String> heard =
                            results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    String best = longestHeard(heard);
                    if (best != null && !best.isEmpty()) {
                        onHeard(best);
                    } else if (!srRetryUsed) {
                        scheduleRecognizerRetry(gen, 200);
                    } else {
                        speakListenFail(gen);
                    }
                }

                @Override
                public void onPartialResults(android.os.Bundle partialResults) {
                }

                @Override
                public void onEvent(int eventType, android.os.Bundle params) {
                }
            });
            Intent ri = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            ri.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            ri.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS,
                    2000);
            ri.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS,
                    2000);
            ri.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1500);
            ri.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5);
            main.removeCallbacks(listenWatch);
            listening = true;
            listenStartedAt = SystemClock.uptimeMillis();
            Log.i(TAG, "SR startListening gen=" + gen);
            recognizer.startListening(ri);
            main.postDelayed(listenWatch, LISTEN_TIMEOUT_MS);
            // Keep listenStarting true until ready/error — clearing early turns
            // ERROR_CLIENT into a hard fail on this OEM.
        } catch (Exception e) {
            Log.e(TAG, "startSpeechFallback", e);
            listenStarting = false;
            tryMuseRecorderOrFail();
        }
    }

    /** Invalidate stale SR callbacks, rebuild engine, start again once. */
    private void scheduleRecognizerRetry(final int fromGen, int delayMs) {
        if (fromGen != listenGen || srRetryUsed) {
            return;
        }
        srRetryUsed = true;
        try {
            AskRouter.stopTts();
        } catch (Exception ignored) {
        }
        destroyRecognizer();
        listenGen++;
        final int retryGen = listenGen;
        readyForSpeech = false;
        listenStarting = true;
        listening = true;
        main.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (retryGen != listenGen) {
                    return;
                }
                startSpeechFallback();
            }
        }, delayMs);
    }

    private void tryMuseRecorderOrFail() {
        museAttempted = true;
        String key = KeyVault.loadKey(this);
        if (key != null && !key.isEmpty() && startRecorder()) {
            listening = true;
            listenStarting = false;
            main.postDelayed(listenWatch, LISTEN_TIMEOUT_MS);
            return;
        }
        listening = false;
        listenStarting = false;
        speakListenFail(listenGen);
    }

    private void speakListenFail() {
        speakListenFail(listenGen);
    }

    private void speakListenFail(int gen) {
        listening = false;
        if (gen == failSpokenGen) {
            return;
        }
        failSpokenGen = gen;
        // Do not re-arm confirm mic via fail TTS.
        confirmListenArmed = false;
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setFail("Again");
            setIslandPhase(IslandBackdropView.STATE_ERROR, false, false);
            main.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (pillView != null && !PaymentGate.isHidden()) {
                        pillView.setState(IslandPillView.STATE_IDLE);
                    }
                    setIslandPhase(IslandBackdropView.STATE_IDLE, false, false);
                }
            }, 1600);
        }
        if (PendingPlan.hasPending()) {
            AskRouter.speak(this, BeeAsk.clampSpeak("Still waiting on your yes."));
        } else {
            AskRouter.speak(this, BeeAsk.clampSpeak("Missed that — say it once more."));
        }
    }

    private void setIslandPhase(int backdropState, boolean waveActive, boolean waveThink) {
        try {
            if (backdropView != null) {
                backdropView.setState(backdropState);
            }
        } catch (Exception ignored) {
        }
        try {
            if (waveView != null) {
                waveView.setMode(waveActive, waveThink);
            }
        } catch (Exception ignored) {
        }
        try {
            confirming = (backdropState == IslandBackdropView.STATE_CONFIRM);
        } catch (Exception ignored) {
        }
    }

    /** Mission/speech line inside the capsule (never below the hit slop). */
    void setIslandLine(final String text) {
        final String line = BeeAsk.clampLine(text == null ? "" : text);
        main.post(new Runnable() {
            @Override
            public void run() {
                try {
                    if (lineView != null) {
                        lineView.setText(line);
                        lineView.setVisibility(line.isEmpty() ? View.GONE : View.VISIBLE);
                    }
                } catch (Exception ignored) {
                }
            }
        });
    }

    void playWaterNow() {
        try {
            if (PaymentGate.isHidden()) {
                return;
            }
            hideHero();
            final HydrationHeroView view = new HydrationHeroView(this);
            view.setHost(new HydrationHeroView.Host() {
                @Override
                public void onOffer() {
                    AskRouter.speak(IslandService.this, "Hey. Drink some water.");
                }

                @Override
                public void onOffering(boolean offering) {
                    if (offering) {
                        showHeroHit(view);
                    } else {
                        hideHeroHit();
                    }
                }

                @Override
                public void onFinished(boolean drank) {
                    hideHeroHit();
                    hideHero();
                    if (pillView != null) {
                        if (drank) {
                            pillView.setSuccess("Drank");
                        }
                        pillView.setState(IslandPillView.STATE_IDLE);
                    }
                }
            });
            int w = getResources().getDisplayMetrics().widthPixels;
            int h = dp(380);
            boolean shown = false;
            // Prefer a11y overlay (same path as the pill) when host is bound.
            if (isHostBound()) {
                shown = IslandAccess.showOverlay(view, w, h, 0, 0, false);
            }
            if (!shown && Settings.canDrawOverlays(this)) {
                if (wm == null) {
                    wm = (WindowManager) getSystemService(WINDOW_SERVICE);
                }
                if (wm != null) {
                    try {
                        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                                w,
                                h,
                                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                                PixelFormat.TRANSLUCENT);
                        lp.gravity = Gravity.TOP | Gravity.START;
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                            lp.layoutInDisplayCutoutMode =
                                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
                        }
                        lp.x = 0;
                        lp.y = 0;
                        wm.addView(view, lp);
                        shown = true;
                    } catch (Exception e) {
                        Log.e(TAG, "playWater app overlay failed", e);
                    }
                }
            }
            if (!shown) {
                AskRouter.speak(this, BeeAsk.clampSpeak(
                        "Need overlay permission for water."));
                return;
            }
            hero = view;
            if (pillView != null) {
                pillView.setStatusText("");
                pillView.setState(IslandPillView.STATE_THINKING);
            }
            setIslandLine("Water");
            view.play();
            getSharedPreferences("bee_water", MODE_PRIVATE)
                    .edit()
                    .putLong("last", System.currentTimeMillis())
                    .apply();
            main.removeCallbacks(hideHero);
            main.postDelayed(hideHero, WaterHero.OFFER_MS + 8000L);
        } catch (Exception e) {
            Log.e(TAG, "playWaterNow", e);
        }
    }

    private void showHeroHit(final HydrationHeroView view) {
        hideHeroHit();
        try {
            View hit = new View(this);
            hit.setClickable(true);
            hit.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    if (view != null) {
                        view.acceptDrink();
                    }
                }
            });
            int w = dp(160);
            int h = dp(160);
            int x = Math.max(0, Math.round(CAMERA_X_PX - w / 2f));
            int y = Math.max(0, Math.round(CAMERA_Y_PX + dp(90)));
            boolean shown = false;
            if (isHostBound()) {
                shown = IslandAccess.showOverlay(hit, w, h, x, y, true);
            }
            if (!shown && Settings.canDrawOverlays(this)) {
                if (wm == null) {
                    wm = (WindowManager) getSystemService(WINDOW_SERVICE);
                }
                if (wm != null) {
                    WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                            w,
                            h,
                            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                                    | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                                    | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                            PixelFormat.TRANSLUCENT);
                    lp.gravity = Gravity.TOP | Gravity.START;
                    lp.x = x;
                    lp.y = y;
                    wm.addView(hit, lp);
                    shown = true;
                }
            }
            if (shown) {
                heroHit = hit;
            }
        } catch (Exception e) {
            Log.e(TAG, "showHeroHit", e);
        }
    }

    private void hideHeroHit() {
        View hit = heroHit;
        heroHit = null;
        if (hit == null) {
            return;
        }
        try {
            IslandAccess.hideOverlay(hit);
        } catch (Exception ignored) {
        }
        try {
            if (wm != null) {
                wm.removeView(hit);
            }
        } catch (Exception ignored) {
        }
    }

    private void hideHero() {
        hideHeroHit();
        HydrationHeroView h = hero;
        hero = null;
        if (h == null) {
            return;
        }
        try {
            h.stop();
        } catch (Exception ignored) {
        }
        try {
            IslandAccess.hideOverlay(h);
        } catch (Exception ignored) {
        }
        try {
            if (wm != null) {
                wm.removeView(h);
            }
        } catch (Exception ignored) {
        }
    }

    private void stopListeningQuiet() {
        listenGen++;
        listenStarting = false;
        readyForSpeech = false;
        confirmListenArmed = false;
        try {
            main.removeCallbacks(listenWatch);
            stopRecorder(false);
            destroyRecognizer();
        } catch (Exception ignored) {
        }
        listening = false;
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setState(IslandPillView.STATE_IDLE);
        }
        setIslandPhase(IslandBackdropView.STATE_IDLE, false, false);
    }

    void ask(String text) {
        onHeard(text);
    }

    private void onHeard(String text) {
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setStatusText("");
            pillView.setState(IslandPillView.STATE_THINKING);
        }
        setIslandLine(BeeAsk.lineFor("plan"));
        setIslandPhase(IslandBackdropView.STATE_THINKING, true, true);
        AskRouter.handle(this, text);
    }

    /** Called when PendingPlan is staged — amber confirm pulse. */
    void showConfirmPulse() {
        showConfirmPulse(BeeAsk.lineFor("confirm"));
    }

    void showConfirmPulse(String prompt) {
        if (PaymentGate.isHidden()) {
            return;
        }
        if (pillView != null) {
            pillView.setStatusText("");
            pillView.setState(IslandPillView.STATE_THINKING);
        }
        String line = (prompt == null || prompt.trim().isEmpty())
                ? BeeAsk.lineFor("confirm") : BeeAsk.clampLine(prompt);
        setIslandLine(line);
        setIslandPhase(IslandBackdropView.STATE_CONFIRM, false, false);
    }

    /** After TTS confirm prompt, open mic for yes/cancel. */
    void listenAfterConfirm() {
        listenAfterConfirm("");
    }

    /**
     * Arm confirm listen: prefer TTS onDone via {@link #listenAfterConfirmReady};
     * fallback timer if TTS never fires.
     */
    void listenAfterConfirm(String spoken) {
        confirmListenArmed = true;
        main.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (confirmListenArmed && PendingPlan.hasPending()) {
                    listenAfterConfirmReady();
                }
            }
        }, 3500);
    }

    /** Called when confirm TTS finishes (or fallback timer). */
    void listenAfterConfirmReady() {
        if (!confirmListenArmed) {
            return;
        }
        confirmListenArmed = false;
        try {
            AskRouter.stopTts();
        } catch (Exception ignored) {
        }
        main.postDelayed(new Runnable() {
            @Override
            public void run() {
                try {
                    if (PendingPlan.hasPending()) {
                        startListening();
                    }
                } catch (Exception ignored) {
                }
            }
        }, 300);
    }

    private static String longestHeard(ArrayList<String> heard) {
        if (heard == null || heard.isEmpty()) {
            return "";
        }
        String best = "";
        for (int i = 0; i < heard.size(); i++) {
            String s = heard.get(i);
            if (s == null) {
                continue;
            }
            s = s.trim();
            if (s.length() > best.length()) {
                best = s;
            }
        }
        return best;
    }

    void showActing() {
        setIslandPhase(IslandBackdropView.STATE_ACTING, false, false);
        setIslandLine(BeeAsk.lineFor("done"));
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setSuccess("");
            main.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (pillView != null && !PaymentGate.isHidden()) {
                        pillView.setState(IslandPillView.STATE_IDLE);
                    }
                    setIslandLine("");
                    setIslandPhase(IslandBackdropView.STATE_IDLE, false, false);
                }
            }, 2200);
        }
    }

    private void hidePill() {
        try {
            if (pillView != null) {
                pillView.setState(IslandPillView.STATE_HIDDEN);
            }
        } catch (Exception ignored) {
        }
        try {
            if (wm != null && pill != null && !isHostBound()) {
                wm.removeView(pill);
            }
        } catch (Exception ignored) {
        }
        pill = null;
        pillView = null;
        backdropView = null;
        waveView = null;
        lineView = null;
        capsule = null;
    }

    private int dp(int v) {
        float d = getResources().getDisplayMetrics().density;
        return Math.round(v * d);
    }
}
