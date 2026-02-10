import type { ControlTimingSettings } from "./types.js";
import { buildUiRendererScript } from "./ui_renderer_script.js";
import { buildUiShellHtml } from "./ui_shell.js";
import { UI_STYLE_CSS } from "./ui_style.js";

export function buildHtml(
  controlTimingSettings: ControlTimingSettings,
  controlDevMode: boolean,
): string {
  const indicatorFadeStepMs = Math.max(
    1,
    Math.round(controlTimingSettings.indicator_fade_step_s * 1000),
  );
  const toastDurationMs = Math.max(
    1,
    Math.round(controlTimingSettings.toast_duration_s * 1000),
  );
  const widgetAutoTickMs = Math.max(
    1,
    Math.round(controlTimingSettings.widget_auto_tick_s * 1000),
  );
  const widgetAutoRefreshDefaultMs = Math.max(
    1,
    Math.round(controlTimingSettings.widget_auto_refresh_default_s * 1000),
  );

  const rendererScript = buildUiRendererScript({
    controlDevMode,
    indicatorFadeStepMs,
    toastDurationMs,
    widgetAutoTickMs,
    widgetAutoRefreshDefaultMs,
  });

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>MiMoLo Control Proto</title>
    <style>
${UI_STYLE_CSS}
    </style>
  </head>
  <body>
${buildUiShellHtml(controlDevMode)}
    <script>
${rendererScript}
    </script>
  </body>
</html>`;
}
