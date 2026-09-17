import { useCallback, useMemo, useState } from "react";
import type { Run } from "../../types/runtime";
import type { RunUiState } from "../../state/runReducer";
import { RuntimeInspector } from "../RuntimeInspector";

/**
 * Agent Inspector panel (chat mode wrapper): owns the selected-stage state and
 * derives stage→artifact mapping, then renders the SAME RuntimeInspector the
 * Developer Mode uses (one inspector, one source of truth).
 */
export function AgentInspectorPanel({
  meta,
  state,
  streaming,
  error,
}: {
  meta: Run | null;
  state: RunUiState;
  streaming: boolean;
  error: string | null;
}) {
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const stageOrder = state.stageOrder.length ? state.stageOrder : (meta?.stage_order ?? []);
  const artifactTypeOf = useCallback(
    (stageId: string): string | null =>
      stageOrder.find((s) => s.id === stageId)?.produces ?? null,
    [stageOrder],
  );
  const inspector = useMemo(
    () => (
      <RuntimeInspector
        meta={meta}
        state={{ ...state, stageOrder }}
        streaming={streaming}
        error={error}
        selectedStage={selectedStage}
        onSelectStage={setSelectedStage}
        artifactTypeOf={artifactTypeOf}
      />
    ),
    [meta, state, stageOrder, streaming, error, selectedStage, artifactTypeOf],
  );
  return inspector;
}
