/** JSON-compatible field values; render imported strings as text. */
export type FieldValue =
  | string
  | number
  | boolean
  | null
  | FieldValue[]
  | { [key: string]: FieldValue };

export interface ObjectFields {
  description: string;
  [field: string]: FieldValue;
}

export interface EventFields extends ObjectFields {
  /** Timezone-qualified timestamp of an actual occurrence. */
  timestamp: string;
}

interface EntityPresentation {
  /** Ontology ID, unique across Objects and Events within the project graph. */
  id: string;
  /** Domain subclass, e.g. Repository, Agent, or ChangeCommitted. */
  type: string;
  /** UI label, separate from domain fields. */
  label: string;
}

export interface GraphObjectEntity extends EntityPresentation {
  kind: 'object';
  /** Inherited description and subclass fields. id is stored at entity.id. */
  fields: ObjectFields;
}

export interface GraphEventEntity extends EntityPresentation {
  kind: 'event';
  /** Inherited timestamp/description and subclass fields. id is entity.id. */
  fields: EventFields;
}

export type GraphEntity = GraphObjectEntity | GraphEventEntity;

/** The complete base Relationship record. Do not add visual metadata here. */
export interface Relationship {
  source: string;
  target: string;
}

export interface GraphRelationship {
  /** UI-only edge identity, unique within the project; not an ontology field. */
  id: string;
  /** Domain relationship subclass, e.g. HasRepository or PerformedBy. */
  type: string;
  relationship: Relationship;
}

/** Explicit scope for one illustrative project, ready for a future read API. */
export interface ProjectGraph {
  id: string;
  name: string;
  description: string;
  entities: GraphEntity[];
  relationships: GraphRelationship[];
}
