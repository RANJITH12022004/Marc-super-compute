package com.bee.island;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
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
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.OvershootInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;

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
    private static final long LISTEN_TIMEOUT_MS = 8000;

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
    private HydrationHeroView hero;
    private View heroHit;
    private SpeechRecognizer recognizer;
    private MediaRecorder recorder;
    private File recordFile;
    private boolean listening;
    private boolean confirming;
    private boolean fallbackUsed;
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
            if (recorder != null) {
                finishRecordAndTranscribe();
                return;
            }
            if (!listening) {
                return;
            }
            try {
                if (recognizer != null) {
                    recognizer.cancel();
                }
            } catch (Exception ignored) {
            }
            speakListenFail();
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
            startForeground(NOTIF_ID, b.build());
        } catch (Exception ignored) {
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

            IslandBackdropView backdrop = new IslandBackdropView(this);
            // Full listen box so morphing status text stays over animated rim.
            FrameLayout.LayoutParams backLp =
                    new FrameLayout.LayoutParams(maxW, maxH);
            backLp.gravity = Gravity.TOP | Gravity.START;
            backLp.leftMargin = listenLeft;
            backLp.topMargin = listenTop;
            backdrop.setLayoutParams(backLp);
            outer.addView(backdrop);
            backdropView = backdrop;

            IslandPillView visual = new IslandPillView(this);
            visual.setAnchorInsets(listenLeft, listenTop, maxW, maxH);
            FrameLayout.LayoutParams visualLp =
                    new FrameLayout.LayoutParams(
                            listening ? maxW : idleW,
                            listening ? maxH : idleH);
            visualLp.gravity = Gravity.TOP | Gravity.START;
            visualLp.leftMargin = listening ? listenLeft : idleLeft;
            visualLp.topMargin = listening ? listenTop : idleTop;
            visual.setLayoutParams(visualLp);
            visual.setDrawCapsule(false);
            if (listening) {
                visual.setStatusText(BeeAsk.lineFor("listen"));
                visual.setState(IslandPillView.STATE_LISTENING);
            } else {
                visual.setState(IslandPillView.STATE_IDLE);
            }
            outer.addView(visual);
            pillView = visual;

            IslandWaveView wave = new IslandWaveView(this);
            FrameLayout.LayoutParams waveLp =
                    new FrameLayout.LayoutParams(dp(28), dp(18));
            waveLp.gravity = Gravity.CENTER_VERTICAL | Gravity.START;
            waveLp.leftMargin = (listening ? listenLeft : idleLeft) + dp(10);
            waveLp.topMargin = (listening ? listenTop : idleTop) + dp(10);
            wave.setLayoutParams(waveLp);
            outer.addView(wave);
            waveView = wave;
            if (listening) {
                setIslandPhase(IslandBackdropView.STATE_LISTENING, true, false);
            } else {
                setIslandPhase(IslandBackdropView.STATE_IDLE, false, false);
            }

            final boolean[] holdFired = new boolean[1];
            final Runnable[] holdRef = new Runnable[1];
            Runnable holdTask = new Runnable() {
                @Override
                public void run() {
                    holdFired[0] = true;
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
                        if ("cancel".equals(tapAction)) {
                            confirming = false;
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
            main.removeCallbacks(listenWatch);
            stopRecorder(false);
            try {
                if (recognizer != null) {
                    recognizer.cancel();
                }
            } catch (Exception ignored) {
            }
            fallbackUsed = false;
            listening = true;
            listenStartedAt = SystemClock.uptimeMillis();
            if (pillView != null) {
                pillView.setStatusText(BeeAsk.lineFor("listen"));
                pillView.setState(IslandPillView.STATE_LISTENING);
            }
            setIslandPhase(IslandBackdropView.STATE_LISTENING, true, false);
            // SpeechRecognizer first: Muse transcribe is a silent 8s record then
            // a POST that usually returns empty, so the user has already stopped
            // talking by the time fallback starts.
            if (SpeechRecognizer.isRecognitionAvailable(this)) {
                startSpeechFallback();
                return;
            }
            String key = KeyVault.loadKey(this);
            if (key != null && !key.isEmpty() && startRecorder()) {
                main.postDelayed(listenWatch, LISTEN_TIMEOUT_MS);
                return;
            }
            startSpeechFallback();
        } catch (Exception ignored) {
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

    private void startSpeechFallback() {
        try {
            if (fallbackUsed) {
                listening = false;
                speakListenFail();
                return;
            }
            fallbackUsed = true;
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                listening = false;
                speakListenFail();
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
                        float norm = 0f;
                        try {
                            // Typical SpeechRecognizer RMS ~ -2..10; map to 0..1.
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
                        listening = false;
                        main.removeCallbacks(listenWatch);
                        speakListenFail();
                    }

                    @Override
                    public void onResults(android.os.Bundle results) {
                        listening = false;
                        main.removeCallbacks(listenWatch);
                        ArrayList<String> heard =
                                results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                        if (heard != null && !heard.isEmpty()) {
                            onHeard(heard.get(0));
                        } else {
                            speakListenFail();
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
            listening = false;
            speakListenFail();
        }
    }

    private void speakListenFail() {
        listening = false;
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setFail("Try again");
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
        AskRouter.speak(this, "Didn't catch that. Try again.");
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

    void playWaterNow() {
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
            try {
                wm.addView(view, lp);
                hero = view;
                if (pillView != null) {
                    pillView.setStatusText("Water");
                    pillView.setState(IslandPillView.STATE_THINKING);
                }
                view.play();
                getSharedPreferences("bee_water", MODE_PRIVATE)
                        .edit()
                        .putLong("last", System.currentTimeMillis())
                        .apply();
                main.removeCallbacks(hideHero);
                main.postDelayed(hideHero, WaterHero.OFFER_MS + 8000L);
            } catch (Exception ignored) {
                hero = null;
            }
        } catch (Exception ignored) {
        }
    }

    private void showHeroHit(final HydrationHeroView view) {
        hideHeroHit();
        try {
            if (wm == null) {
                return;
            }
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
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    w,
                    h,
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                            | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            lp.x = Math.max(0, Math.round(CAMERA_X_PX - w / 2f));
            lp.y = Math.max(0, Math.round(CAMERA_Y_PX + dp(90)));
            wm.addView(hit, lp);
            heroHit = hit;
        } catch (Exception ignored) {
        }
    }

    private void hideHeroHit() {
        try {
            if (heroHit != null && wm != null) {
                wm.removeView(heroHit);
            }
        } catch (Exception ignored) {
        }
        heroHit = null;
    }

    private void hideHero() {
        hideHeroHit();
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

    private void stopListeningQuiet() {
        try {
            main.removeCallbacks(listenWatch);
            if (recognizer != null) {
                recognizer.cancel();
            }
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
            pillView.setStatusText(BeeAsk.lineFor("plan"));
            pillView.setState(IslandPillView.STATE_THINKING);
        }
        setIslandPhase(IslandBackdropView.STATE_THINKING, true, true);
        AskRouter.handle(this, text);
    }

    /** Called when PendingPlan is staged — amber confirm pulse. */
    void showConfirmPulse() {
        if (PaymentGate.isHidden()) {
            return;
        }
        if (pillView != null) {
            pillView.setStatusText(BeeAsk.lineFor("confirm"));
            pillView.setState(IslandPillView.STATE_THINKING);
        }
        setIslandPhase(IslandBackdropView.STATE_CONFIRM, false, false);
    }

    void showActing() {
        setIslandPhase(IslandBackdropView.STATE_ACTING, false, false);
        if (pillView != null && !PaymentGate.isHidden()) {
            pillView.setSuccess(BeeAsk.lineFor("done"));
            main.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (pillView != null && !PaymentGate.isHidden()) {
                        pillView.setState(IslandPillView.STATE_IDLE);
                    }
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
    }

    private int dp(int v) {
        float d = getResources().getDisplayMetrics().density;
        return Math.round(v * d);
    }
}
