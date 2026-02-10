import { buildCardsAndBootstrapSection } from "./ui_renderer_sections/cards_and_bootstrap.js";
import { buildCommandsAndInstallSection } from "./ui_renderer_sections/commands_and_install.js";
import { buildIndicatorsAndWidgetsSection } from "./ui_renderer_sections/indicators_and_widgets.js";
import { buildModalsSection } from "./ui_renderer_sections/modals.js";
import { buildStateAndOpsSection } from "./ui_renderer_sections/state_and_ops.js";

interface UiRendererScriptOptions {
  controlDevMode: boolean;
  indicatorFadeStepMs: number;
  toastDurationMs: number;
  widgetAutoTickMs: number;
  widgetAutoRefreshDefaultMs: number;
}

export function buildUiRendererScript(options: UiRendererScriptOptions): string {
  const {
    controlDevMode,
    indicatorFadeStepMs,
    toastDurationMs,
    widgetAutoTickMs,
    widgetAutoRefreshDefaultMs,
  } = options;

  const sections: string[] = [
    buildStateAndOpsSection(controlDevMode),
    buildModalsSection(toastDurationMs),
    buildIndicatorsAndWidgetsSection(
      indicatorFadeStepMs,
      widgetAutoTickMs,
      widgetAutoRefreshDefaultMs,
    ),
    buildCommandsAndInstallSection(),
    buildCardsAndBootstrapSection(),
  ];

  return sections.join("\n");
}
