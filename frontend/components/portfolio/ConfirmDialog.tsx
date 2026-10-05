'use client';

import React, { useState } from 'react';
import Dialog from './Dialog';
import s from './portfolio.module.css';

interface ConfirmDialogProps {
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  pendingLabel: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export default function ConfirmDialog({
  title,
  description,
  confirmLabel,
  pendingLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);

  const confirm = async () => {
    if (pending) return;
    setPending(true);
    try {
      await onConfirm();
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog title={title} onClose={pending ? () => {} : onCancel} labelledBy="confirm-title">
      <p className={s.dialogText}>{description}</p>
      <div className={s.dialogActions}>
        <button type="button" className={s.btnGhost} onClick={onCancel} disabled={pending}>
          Anuluj
        </button>
        <button type="button" className={s.btnDanger} onClick={() => void confirm()} disabled={pending}>
          {pending ? pendingLabel : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
