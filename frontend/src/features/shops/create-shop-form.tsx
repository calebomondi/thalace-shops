import { useState, type FormEvent } from 'react'

import { Button, ErrorNote, Field, Input, TextArea } from '../../components/ui'
import type { ShopCreate } from '../../lib/api/shops'

type Props = {
  onCreate: (body: ShopCreate) => Promise<unknown>
  onCancel: () => void
}

export function CreateShopForm({ onCreate, onCancel }: Props) {
  const [name, setName] = useState('')
  const [tagline, setTagline] = useState('')
  const [description, setDescription] = useState('')
  const [website, setWebsite] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onCreate({
        name: name.trim(),
        tagline: tagline.trim(),
        description: description.trim(),
        website: website.trim() || undefined,
      })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The shop could not be created.')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-line bg-card p-6 shadow-sm">
      <h2 className="font-display text-xl">A new shop</h2>
      <Field label="Name" hint="Its address is made from the name, e.g. /s/shanga-cad-studio.">
        <Input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Tagline" hint="One line buyers and agents read first.">
        <Input maxLength={200} value={tagline} onChange={(e) => setTagline(e.target.value)} />
      </Field>
      <Field label="What it sells">
        <TextArea maxLength={4000} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label="Website" hint="Optional. The shop's agent can read it to draft offers.">
        <Input type="url" placeholder="https://" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </Field>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="quiet" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving || name.trim().length < 2}>
          {saving ? 'Creating…' : 'Create shop'}
        </Button>
      </div>
    </form>
  )
}
