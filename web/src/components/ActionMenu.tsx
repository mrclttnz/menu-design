import type { ReactElement } from "react";
import { Button, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";
import "./ActionMenu.css";

export interface MenuAction {
  id: string;
  label: string;
  onAction: () => void;
}

export interface ActionMenuProps {
  /** Nome accessibile del pulsante «⋯» (obbligatorio: il pulsante non ha testo visibile). */
  label: string;
  actions: MenuAction[];
}

// Menu «⋯» (UX 9.5): RAC `MenuTrigger` con frecce, Invio, Esc e focus riportato al pulsante.
// Importare questo modulo solo dalle viste che lo usano (code splitting, NFR-001).
export function ActionMenu({ label, actions }: ActionMenuProps): ReactElement {
  return (
    <MenuTrigger>
      <Button className="btn menu-trigger" aria-label={label}>
        <span aria-hidden="true">⋯</span>
      </Button>
      <Popover className="menu-popover">
        <Menu
          className="menu"
          aria-label={label}
          onAction={(key) => actions.find((a) => a.id === key)?.onAction()}
        >
          {actions.map((action) => (
            <MenuItem key={action.id} id={action.id} textValue={action.label} className="menu-item">
              {action.label}
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
