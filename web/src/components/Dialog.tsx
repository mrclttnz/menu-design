import type { ReactElement, ReactNode } from "react";
import { Dialog as AriaDialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import "./Dialog.css";

export interface DialogProps {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  /** `false` per conflitti e conferme irreversibili: Esc e clic fuori non chiudono. */
  dismissable?: boolean;
  kind?: "dialog" | "alert";
  children?: ReactNode;
}

// Modale accessibile (UX 9.5): focus intrappolato, ripristinato all'apertura, titolo come nome.
// Importare questo modulo solo dalle viste che lo usano (code splitting, NFR-001).
export function Dialog({
  title,
  isOpen,
  onClose,
  dismissable = true,
  kind = "dialog",
  children,
}: DialogProps): ReactElement {
  return (
    <ModalOverlay
      className="dialog-overlay"
      isOpen={isOpen}
      isDismissable={dismissable}
      isKeyboardDismissDisabled={!dismissable}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal className="dialog-modal">
        <AriaDialog role={kind === "alert" ? "alertdialog" : "dialog"} className="dialog">
          <Heading slot="title">{title}</Heading>
          {children}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}
