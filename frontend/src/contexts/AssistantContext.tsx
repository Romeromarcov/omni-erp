/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useAssistantChat } from '../hooks/useAssistantChat';

type AssistantChat = ReturnType<typeof useAssistantChat>;

interface AssistantContextType {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
  chat: AssistantChat;
}

const AssistantContext = createContext<AssistantContextType | undefined>(undefined);

export const useAssistant = () => {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error('useAssistant must be used within an AssistantProvider');
  return ctx;
};

export const AssistantProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [open, setOpen] = useState(false);
  const chat = useAssistantChat();

  const value = useMemo(
    () => ({ open, setOpen, toggle: () => setOpen((o) => !o), chat }),
    [open, chat],
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
};
