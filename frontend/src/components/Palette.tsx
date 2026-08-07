/**
 * Paleta de nodos (F3.1). Cada item es arrastrable al canvas (HTML5 DnD): al
 * empezar el arrastre serializa el `PaletteItem` en el dataTransfer; el
 * `FlowCanvas` lo suelta en la posición del cursor.
 */

import { PALETTE, PALETTE_MIME, serializePaletteItem, type PaletteItem } from "../editor/model";

function onDragStart(e: React.DragEvent, item: PaletteItem) {
  e.dataTransfer.setData(PALETTE_MIME, serializePaletteItem(item));
  e.dataTransfer.effectAllowed = "move";
}

export function Palette() {
  return (
    <div className="palette">
      {PALETTE.map((group) => (
        <div key={group.title} className="palette-group">
          <div className="palette-title">{group.title}</div>
          {group.items.map((item) => (
            <div
              key={`${item.kind}:${item.subtype}`}
              className={`palette-item pi-${item.kind}`}
              draggable
              onDragStart={(e) => onDragStart(e, item)}
              title={`Arrastra al canvas: ${item.label}`}
            >
              <span className="palette-icon">{item.icon}</span>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      ))}
      <div className="palette-hint">Arrastra un bloque al lienzo →</div>
    </div>
  );
}
