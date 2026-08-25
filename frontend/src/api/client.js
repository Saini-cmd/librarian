import axios from "axios";
import { API_BASE_URL } from "./config";

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

let getTokenFn = null;

export function setTokenProvider(fn) {
  getTokenFn = fn;
}

client.interceptors.request.use(async (config) => {
  if (getTokenFn) {
    try {
      const token = await getTokenFn();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
    }
  }
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      "Request failed";
    return Promise.reject(new Error(msg));
  }
);

export async function resetAll() {
  const { data } = await client.post("/reset");
  return data;
}

export async function getConversations() {
  const { data } = await client.get("/conversations");
  return data;
}

export async function createConversation(title, repoName, repoUrl) {
  const { data } = await client.post("/conversations", { title, repo_name: repoName, repo_url: repoUrl });
  return data;
}

export async function getConversation(id) {
  const { data } = await client.get(`/conversations/${id}`);
  return data;
}

export async function deleteConversation(id) {
  const { data } = await client.delete(`/conversations/${id}`);
  return data;
}

export async function getRepositories() {
  const { data } = await client.get("/repositories");
  return data;
}

export async function getRepoGraph(repoHash) {
  const { data } = await client.get(`/repositories/${encodeURIComponent(repoHash)}/graph`);
  return data;
}

export async function getFileSummary(repoHash, filePath) {
  const { data } = await client.get(
    `/repositories/${encodeURIComponent(repoHash)}/summary`,
    { params: { file_path: filePath } }
  );
  return data;
}

export async function getChunk(repoHash, chunkId) {
  const { data } = await client.get(
    `/repositories/${encodeURIComponent(repoHash)}/chunks/${encodeURIComponent(chunkId)}`
  );
  return data;
}

export async function getFileChunks(repoHash, filePath) {
  const { data } = await client.get(
    `/repositories/${encodeURIComponent(repoHash)}/chunks`,
    { params: { file_path: filePath } }
  );
  return data;
}

export async function getRepoUpdates(repoHash) {
  const { data } = await client.get(`/repositories/${encodeURIComponent(repoHash)}/updates`);
  return data;
}

export async function getProfile() {
  const { data } = await client.get("/users/me");
  return data;
}

export async function updateProfile(updates) {
  const { data } = await client.patch("/users/me", updates);
  return data;
}

export default client;
