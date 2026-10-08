package com.gustavo.pulaanuncio;

import android.app.Activity;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.net.Inet4Address;

/** Abre a página do controle (assets/web/index.html) em tela cheia. */
public class MainActivity extends Activity {
    private WebView web;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);  // tela não apaga usando o touchpad
        getWindow().setStatusBarColor(Color.BLACK);

        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);  // lista de máquinas fica no localStorage
        s.setAllowFileAccess(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        web.setWebViewClient(new WebViewClient());
        web.addJavascriptInterface(this, "Android");  // a página pergunta a rede do celular
        setContentView(web);

        if (estado != null) web.restoreState(estado);
        else web.loadUrl("file:///android_asset/web/index.html");
    }

    @Override
    protected void onSaveInstanceState(Bundle estado) {
        super.onSaveInstanceState(estado);
        web.saveState(estado);
    }

    /** "192.168.100" — os 3 primeiros números do IPv4 do celular na rede atual, ou "" sem rede. */
    @JavascriptInterface
    public String rede() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        LinkProperties lp = cm == null ? null : cm.getLinkProperties(cm.getActiveNetwork());
        if (lp == null) return "";
        for (LinkAddress la : lp.getLinkAddresses()) {
            if (la.getAddress() instanceof Inet4Address) {
                String ip = la.getAddress().getHostAddress();
                return ip.substring(0, ip.lastIndexOf('.'));
            }
        }
        return "";
    }

    @Override
    public void onBackPressed() {
        finish();
    }
}
