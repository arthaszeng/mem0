import { useState } from 'react';
import api from '@/lib/api';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '@/store/store';
import { setApps, setTotalApps, setTotalMemories } from '@/store/profileSlice';
import { useProjectSlug } from './useProjectSlug';

export interface SimpleMemory {
  id: string;
  text: string;
  created_at: string;
  state: string;
  categories: string[];
  app_name: string;
}

interface APIStatsResponse {
  total_memories: number;
  total_apps: number;
  apps: any[];
}

interface UseMemoriesApiReturn {
  fetchStats: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export const useStats = (): UseMemoriesApiReturn => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const projectSlug = useProjectSlug();

  const fetchStats = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = projectSlug ? `?project_slug=${projectSlug}` : '';
      const response = await api.get<APIStatsResponse>(`/api/v1/stats${params}`);
      dispatch(setTotalMemories(response.data.total_memories));
      dispatch(setTotalApps(response.data.total_apps));
      dispatch(setApps(response.data.apps));
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to fetch stats';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return { fetchStats, isLoading, error };
};
