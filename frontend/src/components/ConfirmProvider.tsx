import { useEffect, useRef, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ConfirmContext, type Confirm } from "../useConfirm";

/** 统一的确认纸笺：默认焦点在取消，Esc/遮罩均取消，关闭后归还焦点。 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<HTMLElement | null>(null);
  useEffect(() => () => { resolveRef.current?.(false); }, []);

  const confirm: Confirm = (next) => {
    resolveRef.current?.(false);
    originRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setMessage(next);
    return new Promise<boolean>((resolve) => { resolveRef.current = resolve; });
  };
  const close = (accepted: boolean) => {
    resolveRef.current?.(accepted);
    resolveRef.current = null;
    setMessage(null);
  };
  return <ConfirmContext.Provider value={confirm}>
    {children}
    <Dialog.Root open={message !== null} onOpenChange={(open) => { if (!open) close(false); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="ds-overlay" />
        <Dialog.Content className="ds-dialog" role="alertdialog"
          onOpenAutoFocus={(event) => { event.preventDefault(); cancelRef.current?.focus(); }}
          onCloseAutoFocus={(event) => { event.preventDefault(); originRef.current?.focus(); }}>
          <Dialog.Title>确认操作</Dialog.Title>
          <Dialog.Description className="confirm-message">{message}</Dialog.Description>
          <div className="ds-dialog-actions">
            <button ref={cancelRef} className="btn" onClick={() => close(false)}>取消</button>
            <button className="btn btn-primary" onClick={() => close(true)}>确认</button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </ConfirmContext.Provider>;
}
