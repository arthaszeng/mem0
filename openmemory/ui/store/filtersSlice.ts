import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Category {
  id: string;
  name: string;
  description: string;
  updated_at: string;
  created_at: string;
}

export interface FiltersState {
  apps: {
    selectedApps: string[];
    selectedCategories: string[];
    selectedDomains: string[];
    selectedMemoryType: string;
    selectedAgentId: string;
    sortColumn: string;
    sortDirection: 'asc' | 'desc';
    showArchived: boolean;
  };
  categories: {
    items: Category[];
    total: number;
    isLoading: boolean;
    error: string | null;
  };
  domains: {
    items: string[];
    total: number;
    isLoading: boolean;
    error: string | null;
  };
}

const initialState: FiltersState = {
  apps: {
    selectedApps: [],
    selectedCategories: [],
    selectedDomains: [],
    selectedMemoryType: '',
    selectedAgentId: '',
    sortColumn: 'created_at',
    sortDirection: 'desc',
    showArchived: false,
  },
  categories: {
    items: [],
    total: 0,
    isLoading: false,
    error: null
  },
  domains: {
    items: [],
    total: 0,
    isLoading: false,
    error: null
  }
};

const filtersSlice = createSlice({
  name: 'filters',
  initialState,
  reducers: {
    setCategoriesLoading: (state) => {
      state.categories.isLoading = true;
      state.categories.error = null;
    },
    setCategoriesSuccess: (state, action: PayloadAction<{ categories: Category[]; total: number }>) => {
      state.categories.items = action.payload.categories;
      state.categories.total = action.payload.total;
      state.categories.isLoading = false;
      state.categories.error = null;
    },
    setCategoriesError: (state, action: PayloadAction<string>) => {
      state.categories.isLoading = false;
      state.categories.error = action.payload;
    },
    setDomainsLoading: (state) => {
      state.domains.isLoading = true;
      state.domains.error = null;
    },
    setDomainsSuccess: (state, action: PayloadAction<{ domains: string[]; total: number }>) => {
      state.domains.items = action.payload.domains;
      state.domains.total = action.payload.total;
      state.domains.isLoading = false;
      state.domains.error = null;
    },
    setDomainsError: (state, action: PayloadAction<string>) => {
      state.domains.isLoading = false;
      state.domains.error = action.payload;
    },
    setSelectedApps: (state, action: PayloadAction<string[]>) => {
      state.apps.selectedApps = action.payload;
    },
    setSelectedCategories: (state, action: PayloadAction<string[]>) => {
      state.apps.selectedCategories = action.payload;
    },
    setSelectedDomains: (state, action: PayloadAction<string[]>) => {
      state.apps.selectedDomains = action.payload;
    },
    setShowArchived: (state, action: PayloadAction<boolean>) => {
      state.apps.showArchived = action.payload;
    },
    setSelectedMemoryType: (state, action: PayloadAction<string>) => {
      state.apps.selectedMemoryType = action.payload;
    },
    setSelectedAgentId: (state, action: PayloadAction<string>) => {
      state.apps.selectedAgentId = action.payload;
    },
    clearFilters: (state) => {
      state.apps.selectedApps = [];
      state.apps.selectedCategories = [];
      state.apps.selectedDomains = [];
      state.apps.selectedMemoryType = '';
      state.apps.selectedAgentId = '';
      state.apps.showArchived = false;
    },
    setSortingState: (state, action: PayloadAction<{ column: string; direction: 'asc' | 'desc' }>) => {
      state.apps.sortColumn = action.payload.column;
      state.apps.sortDirection = action.payload.direction;
    },
  },
});

export const {
  setCategoriesLoading,
  setCategoriesSuccess,
  setCategoriesError,
  setDomainsLoading,
  setDomainsSuccess,
  setDomainsError,
  setSelectedApps,
  setSelectedCategories,
  setSelectedDomains,
  setSelectedMemoryType,
  setSelectedAgentId,
  setShowArchived,
  clearFilters,
  setSortingState
} = filtersSlice.actions;

export default filtersSlice.reducer; 