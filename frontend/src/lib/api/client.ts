import { accessToken } from '../supabase'

/** A refusal from the API, with the message the backend wrote for people. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Detail = string | { msg?: string }[] | undefined

function message(detail: Detail, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return `Something went wrong (${status}). Try again.`
}

/** Every call to the backend goes through here: same origin, signed in. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: Detail }
    throw new ApiError(response.status, message(body.detail, response.status))
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}
