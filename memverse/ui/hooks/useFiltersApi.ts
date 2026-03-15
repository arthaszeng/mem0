import { useState, useCallback } from 'react';
import api from '@/lib/api';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '@/store/store';
import {
  Category,
  setCategoriesLoading,
  setCategoriesSuccess,
  setCategoriesError,
  setDomainsLoading,
  setDomainsSuccess,
  setDomainsError,
  setSortingState,
  setSelectedApps,
  setSelectedCategories
} from '@/store/filtersSlice';
import { useProjectSlug } from './useProjectSlug';

interface CategoriesResponse {
  categories: Category[];
  total: number;
}

interface DomainsResponse {
  domains: string[];
  total: number;
}

export interface UseFiltersApiReturn {
  fetchCategories: () => Promise<void>;
  fetchDomains: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
  updateApps: (apps: string[]) => void;
  updateCategories: (categories: string[]) => void;
  updateSort: (column: string, direction: 'asc' | 'desc') => void;
}

export const useFiltersApi = (): UseFiltersApiReturn => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const projectSlug = useProjectSlug();

  const fetchCategories = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    dispatch(setCategoriesLoading());
    try {
      const params = projectSlug ? `?project_slug=${projectSlug}` : '';
      const response = await api.get<CategoriesResponse>(
        `/api/v1/memories/categories${params}`
      );
      dispatch(setCategoriesSuccess({
        categories: response.data.categories,
        total: response.data.total
      }));
      setIsLoading(false);
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to fetch categories';
      setError(errorMessage);
      dispatch(setCategoriesError(errorMessage));
      setIsLoading(false);
      throw new Error(errorMessage);
    }
  }, [dispatch, projectSlug]);

  const fetchDomains = useCallback(async (): Promise<void> => {
    dispatch(setDomainsLoading());
    try {
      const params = projectSlug ? `?project_slug=${projectSlug}` : '';
      const response = await api.get<DomainsResponse>(
        `/api/v1/memories/domains${params}`
      );
      dispatch(setDomainsSuccess({
        domains: response.data.domains,
        total: response.data.total
      }));
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to fetch domains';
      dispatch(setDomainsError(errorMessage));
    }
  }, [dispatch, projectSlug]);

  const updateApps = useCallback((apps: string[]) => {
    dispatch(setSelectedApps(apps));
  }, [dispatch]);

  const updateCategories = useCallback((categories: string[]) => {
    dispatch(setSelectedCategories(categories));
  }, [dispatch]);

  const updateSort = useCallback((column: string, direction: 'asc' | 'desc') => {
    dispatch(setSortingState({ column, direction }));
  }, [dispatch]);

  return {
    fetchCategories,
    fetchDomains,
    isLoading,
    error,
    updateApps,
    updateCategories,
    updateSort
  };
};
