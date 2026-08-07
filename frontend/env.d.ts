/// <reference types="next" />

declare namespace NodeJS {
  interface ProcessEnv {
    /** API Gateway URL - defaults to http://localhost:8000/v1 */
    readonly VITE_API_GATEWAY_URL ?: string
  }
}
