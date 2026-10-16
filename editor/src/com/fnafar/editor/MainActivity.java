package com.fnafar.editor;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Editor for the save files of the FNAF AR offline server.
 * The UI lives in assets/index.html; this class only opens the WebView and
 * provides a file read/write bridge ("Android") under /sdcard/FNAFAR_server.
 */
public class MainActivity extends Activity {
    private static final int PERMISSION_REQUEST = 1;
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        web.addJavascriptInterface(new Bridge(), "Android");
        setContentView(web);

        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{
                    Manifest.permission.READ_EXTERNAL_STORAGE,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE}, PERMISSION_REQUEST);
        } else {
            loadUi();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        loadUi();
    }

    private void loadUi() {
        web.loadUrl("file:///android_asset/index.html");
    }

    private static File base() {
        return new File(Environment.getExternalStorageDirectory(), "FNAFAR_server");
    }

    private static File resolve(String rel) {
        if (rel == null || rel.contains("..")) {
            throw new IllegalArgumentException("invalid path: " + rel);
        }
        return new File(base(), rel);
    }

    private static byte[] readAll(InputStream in) throws Exception {
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        } finally {
            in.close();
        }
    }

    private static void copy(File src, File dst) throws Exception {
        byte[] data = readAll(new FileInputStream(src));
        OutputStream out = new FileOutputStream(dst);
        try {
            out.write(data);
        } finally {
            out.close();
        }
    }

    /** Called from JavaScript as "Android.xxx()". */
    private class Bridge {
        @JavascriptInterface
        public String basePath() {
            return base().getAbsolutePath();
        }

        @JavascriptInterface
        public boolean hasPermission() {
            return checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface
        public boolean exists(String rel) {
            return resolve(rel).exists();
        }

        /** File contents, or null if the file is missing or unreadable. */
        @JavascriptInterface
        public String read(String rel) {
            try {
                File f = resolve(rel);
                if (!f.isFile()) {
                    return null;
                }
                return new String(readAll(new FileInputStream(f)), StandardCharsets.UTF_8);
            } catch (Exception e) {
                return null;
            }
        }

        /**
         * Writes to a .tmp file first, then moves it into place. Keeps the previous
         * version as .bak. Returns an empty string on success, an error message otherwise.
         */
        @JavascriptInterface
        public String write(String rel, String content) {
            try {
                File f = resolve(rel);
                File dir = f.getParentFile();
                if (dir != null && !dir.isDirectory() && !dir.mkdirs()) {
                    return "could not create folder: " + dir;
                }
                File tmp = new File(f.getPath() + ".tmp");
                OutputStream out = new FileOutputStream(tmp);
                try {
                    out.write(content.getBytes(StandardCharsets.UTF_8));
                } finally {
                    out.close();
                }
                if (f.exists()) {
                    copy(f, new File(f.getPath() + ".bak"));
                    if (!f.delete()) {
                        return "could not delete old file: " + f;
                    }
                }
                if (!tmp.renameTo(f)) {
                    return "could not move file into place: " + f;
                }
                return "";
            } catch (Exception e) {
                return String.valueOf(e);
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
