import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface LLMConfig {
  model: string;
  temperature: number;
  max_tokens: number;
  api_key?: string;
  ollama_base_url?: string;
}

export interface LLMProvider {
  provider: string;
  config: LLMConfig;
}

export interface EmbedderConfig {
  model: string;
  api_key?: string;
  ollama_base_url?: string;
}

export interface EmbedderProvider {
  provider: string;
  config: EmbedderConfig;
}

export interface VectorStoreConfig {
  [key: string]: any;
}

export interface VectorStoreProvider {
  provider: string;
  config: VectorStoreConfig;
}

export interface Mem0Config {
  llm?: LLMProvider;
  embedder?: EmbedderProvider;
  vector_store?: VectorStoreProvider;
}

export interface MemverseConfig {
  custom_instructions?: string | null;
}

export interface ConfigState {
  memverse: MemverseConfig;
  mem0: Mem0Config;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: ConfigState = {
  memverse: {
    custom_instructions: null,
  },
  mem0: {
    llm: {
      provider: 'openai',
      config: {
        model: 'gpt-4o-mini',
        temperature: 0.1,
        max_tokens: 2000,
        api_key: 'env:OPENAI_API_KEY',
      },
    },
    embedder: {
      provider: 'openai',
      config: {
        model: 'text-embedding-3-small',
        api_key: 'env:OPENAI_API_KEY',
      },
    },
    vector_store: {
      provider: 'qdrant',
      config: {
        host: 'memverse_store',
        port: 6333,
        collection_name: 'memverse',
        embedding_model_dims: 1536,
      },
    },
  },
  status: 'idle',
  error: null,
};

const configSlice = createSlice({
  name: 'config',
  initialState,
  reducers: {
    setConfigLoading: (state) => {
      state.status = 'loading';
      state.error = null;
    },
    setConfigSuccess: (state, action: PayloadAction<{ memverse?: MemverseConfig; openmemory?: MemverseConfig; mem0: Mem0Config }>) => {
      const memverseCfg = action.payload.memverse ?? action.payload.openmemory;
      if (memverseCfg) {
        state.memverse = memverseCfg;
      }
      state.mem0 = action.payload.mem0;
      state.status = 'succeeded';
      state.error = null;
    },
    setConfigError: (state, action: PayloadAction<string>) => {
      state.status = 'failed';
      state.error = action.payload;
    },
    updateMemverse: (state, action: PayloadAction<MemverseConfig>) => {
      state.memverse = action.payload;
    },
    updateLLM: (state, action: PayloadAction<LLMProvider>) => {
      state.mem0.llm = action.payload;
    },
    updateEmbedder: (state, action: PayloadAction<EmbedderProvider>) => {
      state.mem0.embedder = action.payload;
    },
    updateVectorStore: (state, action: PayloadAction<VectorStoreProvider>) => {
      state.mem0.vector_store = action.payload;
    },
    updateMem0Config: (state, action: PayloadAction<Mem0Config>) => {
      state.mem0 = action.payload;
    },
  },
});

export const {
  setConfigLoading,
  setConfigSuccess,
  setConfigError,
  updateMemverse,
  updateLLM,
  updateEmbedder,
  updateVectorStore,
  updateMem0Config,
} = configSlice.actions;

export default configSlice.reducer; 