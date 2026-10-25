'use client';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Customer } from '@/lib/types';

interface CustomerContextType {
  selectedCustomer: Customer | null;
  setSelectedCustomer: (c: Customer) => void;
  allCustomers: Customer[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

const CustomerContext = createContext<CustomerContextType | null>(null);

/** Scored customers from the latest mainframe batch run, shared by every page. */
export function CustomerProvider({ children }: { children: React.ReactNode }) {
  const [allCustomers, setAll] = useState<Customer[]>([]);
  const [selectedCustomer, setSelected] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.get<Customer[]>('/customers');
      setAll(list);
      setError(null);
      setSelected(prev => (prev && list.find(c => c.id === prev.id)) || list[0] || null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return (
    <CustomerContext.Provider value={{
      selectedCustomer, setSelectedCustomer: setSelected, allCustomers, loading, error, reload,
    }}>
      {children}
    </CustomerContext.Provider>
  );
}

export function useCustomer() {
  const ctx = useContext(CustomerContext);
  if (!ctx) throw new Error('useCustomer must be used inside CustomerProvider');
  return ctx;
}
