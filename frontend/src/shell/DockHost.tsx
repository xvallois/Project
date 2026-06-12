/** DockHost: the dockview root + panel registry + PanelFrame chrome.
 *
 * The PanelModule contract (design v1.0 §4.2) keeps this file the ONLY
 * place that knows dockview's API — panels receive typed params and the
 * link-group context, nothing else.
 */
import { DockviewReact, type AddPanelOptions, type DockviewApi,
  type DockviewReadyEvent, type IDockviewPanelProps } from "dockview";
import { useEffect, useRef } from "react";

import type { LinkGroupId, Pair, PanelKind, Tenor } from "../core/types";
import { useUi, useWorkspaces, type OpenPanelRequest } from "../state/stores";
import { BlotPanel } from "../panels/BlotPanel";
import { HlthPanel } from "../panels/HlthPanel";
import { KeysPanel } from "../panels/KeysPanel";
import { OppsPanel } from "../panels/OppsPanel";
import { OppsLivePanel } from "../panels/OppsLivePanel";
import { useEngine } from "../state/engine";
import { RchpPanel } from "../panels/RchpPanel";
import { SigsPanel } from "../panels/SigsPanel";
import { SmilePanel } from "../panels/SmilePanel";
import { VheatPanel } from "../panels/VheatPanel";

export interface PanelParams {
  kind: PanelKind;
  link: LinkGroupId | null;
  pair?: Pair;
  tenor?: Tenor;
  zMin?: number;
}

/** Resolve a panel's effective context: link group wins when linked. */
export function usePanelContext(p: PanelParams): { pair: Pair; tenor: Tenor } {
  const groups = useUi((s) => s.linkGroups);
  if (p.link && groups[p.link]) return groups[p.link]!;
  return { pair: p.pair ?? "EURUSD", tenor: p.tenor ?? "3M" };
}

const TITLES: Partial<Record<PanelKind, string>> = {
  OPPS: "Opportunity feed", VHEAT: "Surface", SMIL: "Smile",
  RCHP: "Rich/cheap", SIGS: "Signal monitor", BLOT: "Decision ledger",
  HLTH: "Health", KEYS: "Keyboard map",
};

const BODIES: Partial<Record<PanelKind,
  React.FC<{ params: PanelParams }>>> = {
  OPPS: OppsPanel, VHEAT: VheatPanel, SMIL: SmilePanel, RCHP: RchpPanel,
  SIGS: SigsPanel, BLOT: BlotPanel, HLTH: HlthPanel, KEYS: KeysPanel,
};

const LINK_ORDER: (LinkGroupId | null)[] = [null, "A", "B", "C", "D"];

function PanelFrame(props: IDockviewPanelProps<PanelParams>) {
  const params = props.params;
  const setFocused = useUi((s) => s.setFocused);
  const liveEngine = useEngine((s) => s.connected) === true;
  const Body = params.kind === "OPPS" && liveEngine
    ? OppsLivePanel : BODIES[params.kind];

  const cycleLink = () => {
    const i = LINK_ORDER.indexOf(params.link);
    const next = LINK_ORDER[(i + 1) % LINK_ORDER.length];
    props.api.updateParameters({ ...params, link: next });
  };

  return (
    <div className="panelframe"
      onFocusCapture={() => setFocused(props.api.id)}
      onMouseDownCapture={() => setFocused(props.api.id)}>
      <div className="ph">
        <span className="mn">{params.kind}</span>
        <span className="tt">{TITLES[params.kind]}</span>
        <button className={`link l${params.link ?? "none"}`}
          title="link group (Alt+A/B/C/D)" onClick={cycleLink}>
          {params.link ?? "–"}
        </button>
      </div>
      <div className="pb">
        {Body ? <Body params={params} /> :
          <div className="phase-note">
            {params.kind} ships in a later phase — mnemonic reserved.
          </div>}
      </div>
    </div>
  );
}

const components = { frame: PanelFrame };

let counter = 0;
function addPanel(api: DockviewApi, req: OpenPanelRequest,
                  position?: AddPanelOptions["position"]) {
  const params: PanelParams = {
    kind: req.kind,
    link: req.pair ? null : "A",          // explicit pair = pinned panel
    pair: req.pair, tenor: req.tenor, zMin: req.zMin,
  };
  api.addPanel({
    id: `${req.kind.toLowerCase()}-${counter++}`,
    component: "frame",
    title: req.kind,
    params,
    ...(position ? { position } : {}),
  });
}

function defaultLayout(api: DockviewApi) {
  addPanel(api, { kind: "OPPS" });
  addPanel(api, { kind: "VHEAT" },
    { referencePanel: api.panels[0].id, direction: "right" });
  addPanel(api, { kind: "SMIL" },
    { referencePanel: api.panels[1].id, direction: "below" });
  addPanel(api, { kind: "RCHP" },
    { referencePanel: api.panels[2].id, direction: "right" });
  addPanel(api, { kind: "SIGS" },
    { referencePanel: api.panels[1].id, direction: "right" });
  addPanel(api, { kind: "HLTH" },
    { referencePanel: api.panels[4].id, direction: "below" });
}

export function DockHost() {
  const setDockApi = useWorkspaces((s) => s.setDockApi);
  const markDirty = useWorkspaces((s) => s.markDirty);
  const apiRef = useRef<DockviewApi | null>(null);

  const onReady = (e: DockviewReadyEvent) => {
    apiRef.current = e.api;
    setDockApi({
      openPanel: (req) => {
        // focus an existing unpinned panel of this kind, else open new
        const existing = e.api.panels.find((p) =>
          (p.params as PanelParams | undefined)?.kind === req.kind);
        if (existing && !req.pair) { existing.api.setActive(); return; }
        addPanel(e.api, req);
      },
      toJSON: () => e.api.toJSON(),
      fromJSON: (layout) => {
        e.api.clear();
        if (layout) e.api.fromJSON(layout as never);
        else defaultLayout(e.api);
      },
    });
    defaultLayout(e.api);
    e.api.onDidLayoutChange(() => markDirty());
  };

  useEffect(() => () => setDockApi(null), [setDockApi]);

  return (
    <DockviewReact components={components} onReady={onReady}
      className="dockview-theme-dark" />
  );
}
