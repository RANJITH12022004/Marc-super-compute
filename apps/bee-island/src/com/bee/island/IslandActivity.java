package com.bee.island;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.ToggleButton;

import androidx.core.app.ActivityCompat;

import java.util.ArrayList;
import java.util.List;

/** Apple-quality Island · Chat · Setup. Composer uses AskRouter (same DAG as the pill). */
public class IslandActivity extends Activity implements ChatStore.Listener {

    private View islandPage;
    private View chatPage;
    private View setupPage;
    private Button navIsland;
    private Button navChat;
    private Button navSetup;
    private ListView chatList;
    private ArrayAdapter<String> chatAdapter;
    private final List<String> chatLines = new ArrayList<String>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_home);

        islandPage = findViewById(R.id.island_page);
        chatPage = findViewById(R.id.chat_page);
        setupPage = findViewById(R.id.setup_page);
        navIsland = findViewById(R.id.nav_island);
        navChat = findViewById(R.id.nav_chat);
        navSetup = findViewById(R.id.nav_setup);
        chatList = findViewById(R.id.chat_list);
        chatAdapter = new ArrayAdapter<String>(this, R.layout.item_chat, R.id.bubble, chatLines);
        if (chatList != null) {
            chatList.setAdapter(chatAdapter);
        }

        if (navIsland != null) {
            navIsland.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    showPage(0);
                }
            });
        }
        if (navChat != null) {
            navChat.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    showPage(1);
                }
            });
        }
        if (navSetup != null) {
            navSetup.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    showPage(2);
                }
            });
        }

        View listen = findViewById(R.id.listen_button);
        if (listen != null) {
            listen.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    startIsland(IslandService.ACTION_LISTEN, null);
                }
            });
        }
        View overlay = findViewById(R.id.enable_overlay);
        if (overlay != null) {
            overlay.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:" + getPackageName()));
                    startActivity(i);
                }
            });
        }
        View mic = findViewById(R.id.enable_mic);
        if (mic != null) {
            mic.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    ActivityCompat.requestPermissions(IslandActivity.this,
                            new String[]{Manifest.permission.RECORD_AUDIO}, 41);
                }
            });
        }
        View a11y = findViewById(R.id.enable_accessibility);
        if (a11y != null) {
            a11y.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
                }
            });
        }
        View send = findViewById(R.id.send_button);
        final EditText composer = findViewById(R.id.composer);
        if (send != null) {
            send.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    sendComposer(composer);
                }
            });
        }
        View yes = findViewById(R.id.confirm_yes);
        if (yes != null) {
            yes.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    AskRouter.handle(IslandActivity.this, "yes");
                }
            });
        }
        View cancel = findViewById(R.id.confirm_cancel);
        if (cancel != null) {
            cancel.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    AskRouter.handle(IslandActivity.this, "cancel");
                }
            });
        }
        View save = findViewById(R.id.save_key);
        final EditText keyBox = findViewById(R.id.api_key);
        if (save != null) {
            save.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    saveKey(keyBox);
                }
            });
        }
        View water = findViewById(R.id.play_water);
        if (water != null) {
            water.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    startIsland(IslandService.ACTION_PLAY_WATER, null);
                }
            });
        }
        View sandbox = findViewById(R.id.mode_sandbox);
        View live = findViewById(R.id.mode_live);
        if (sandbox != null) {
            sandbox.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    KeyVault.saveModels(IslandActivity.this, null, null, null, "sandbox");
                }
            });
        }
        if (live != null) {
            live.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    KeyVault.saveModels(IslandActivity.this, null, null, null, "live");
                }
            });
        }
        final EditText rox = findViewById(R.id.rox_host);
        if (rox != null) {
            SharedPreferences p = getSharedPreferences("bee_setup", MODE_PRIVATE);
            rox.setText(p.getString("rox_url", ""));
            rox.setOnFocusChangeListener(new View.OnFocusChangeListener() {
                @Override
                public void onFocusChange(View v, boolean hasFocus) {
                    if (!hasFocus) {
                        p.edit().putString("rox_url", rox.getText().toString().trim()).apply();
                    }
                }
            });
        }
        ToggleButton driving = findViewById(R.id.driving_toggle);
        if (driving != null) {
            SharedPreferences p = getSharedPreferences("bee_setup", MODE_PRIVATE);
            driving.setChecked(p.getBoolean("driving", false));
            driving.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    p.edit().putBoolean("driving", driving.isChecked()).apply();
                }
            });
        }

        ChatStore.setListener(this);
        refreshChat();
        refreshMask();
        showPage(0);
        startIsland(null, null);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshPermissions();
        refreshMask();
        refreshChat();
    }

    @Override
    protected void onDestroy() {
        ChatStore.setListener(null);
        super.onDestroy();
    }

    @Override
    public void onChat() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                refreshChat();
            }
        });
    }

    private void showPage(int index) {
        if (islandPage != null) {
            islandPage.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        }
        if (chatPage != null) {
            chatPage.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        }
        if (setupPage != null) {
            setupPage.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        }
        tint(navIsland, index == 0);
        tint(navChat, index == 1);
        tint(navSetup, index == 2);
        if (index == 0 && islandPage != null && islandPage.getLayoutParams() != null) {
            islandPage.getLayoutParams().height = ViewGroup.LayoutParams.MATCH_PARENT;
        }
    }

    private void tint(Button b, boolean on) {
        if (b == null) {
            return;
        }
        b.setTextColor(on ? 0xFFE8B15A : 0xFFF5F5F7);
    }

    private void sendComposer(EditText composer) {
        if (composer == null) {
            return;
        }
        String text = composer.getText() == null ? "" : composer.getText().toString().trim();
        if (text.isEmpty()) {
            return;
        }
        composer.setText("");
        AskRouter.handle(this, text);
    }

    private void saveKey(EditText box) {
        if (box == null) {
            return;
        }
        String key = box.getText() == null ? "" : box.getText().toString().trim();
        if (key.isEmpty()) {
            return;
        }
        try {
            KeyVault.saveKey(this, key);
            box.setText("");
            refreshMask();
        } catch (Exception ignored) {
        }
    }

    private void refreshMask() {
        TextView mask = findViewById(R.id.masked_key);
        if (mask == null) {
            return;
        }
        String shown = KeyVault.maskOrEmpty(this);
        mask.setText(shown.isEmpty() ? "No key saved" : shown);
    }

    private void refreshChat() {
        chatLines.clear();
        for (ChatStore.Line line : ChatStore.snapshot(this)) {
            chatLines.add(line.text);
        }
        if (chatAdapter != null) {
            chatAdapter.notifyDataSetChanged();
        }
        boolean pending = PendingPlan.hasPending();
        View confirmRow = findViewById(R.id.confirm_row);
        if (confirmRow != null) {
            confirmRow.setVisibility(pending ? View.VISIBLE : View.GONE);
        }
        View yesView = findViewById(R.id.confirm_yes);
        View cancelView = findViewById(R.id.confirm_cancel);
        String prompt = PendingPlan.prompt();
        if (prompt == null) {
            prompt = "";
        }
        prompt = prompt.trim();
        if (prompt.isEmpty()) {
            prompt = "this";
        }
        if (yesView instanceof TextView) {
            ((TextView) yesView).setText(prompt);
        }
        if (cancelView instanceof TextView) {
            ((TextView) cancelView).setText("that");
        }
    }

    private void refreshPermissions() {
        // Quiet: never nag, never fire settings dumps on Island open.
    }

    private void startIsland(String action, String text) {
        Intent i = new Intent(this, IslandService.class);
        if (action != null) {
            i.setAction(action);
        }
        if (text != null) {
            i.putExtra("text", text);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(i);
        } else {
            startService(i);
        }
    }
}
