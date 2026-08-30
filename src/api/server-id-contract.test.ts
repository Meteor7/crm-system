import { describe, expectTypeOf, it } from 'vitest'
import type { CrmApi } from './contracts'
import type {
  CreateContactInput,
  CreateLeadInput,
  CreateStakeholderInput,
  AddEvaluationRunInput,
  CreateTestRunInput,
  UpdateContactInput,
  UpdateLeadInput,
  UpdateStakeholderInput,
} from '@/types/crm'
import type {
  CreateOpportunityActionInput,
  CreateOpportunityStakeholderInput,
  UpdateOpportunityActionInput,
  UpdateOpportunityStakeholderInput,
} from '@/types/workspaces'

describe('server-owned primary ID contract', () => {
  it('keeps primary IDs out of Contact, Lead, and legacy Stakeholder inputs', () => {
    expectTypeOf<CreateContactInput>().not.toHaveProperty('id')
    expectTypeOf<UpdateContactInput>().not.toHaveProperty('id')
    expectTypeOf<CreateLeadInput>().not.toHaveProperty('id')
    expectTypeOf<UpdateLeadInput>().not.toHaveProperty('id')
    expectTypeOf<CreateStakeholderInput>().not.toHaveProperty('id')
    expectTypeOf<UpdateStakeholderInput>().not.toHaveProperty('id')
  })

  it('keeps IDs out of Opportunity relation and Test Run create inputs', () => {
    expectTypeOf<CreateOpportunityStakeholderInput>().not.toHaveProperty('id')
    expectTypeOf<UpdateOpportunityStakeholderInput>().not.toHaveProperty('id')
    expectTypeOf<CreateOpportunityActionInput>().not.toHaveProperty('id')
    expectTypeOf<UpdateOpportunityActionInput>().not.toHaveProperty('id')
    expectTypeOf<CreateTestRunInput>().not.toHaveProperty('id')
  })

  it('exposes separate create and update methods', () => {
    expectTypeOf<Parameters<CrmApi['createContact']>>().toEqualTypeOf<[CreateContactInput]>()
    expectTypeOf<Parameters<CrmApi['updateContact']>>().toEqualTypeOf<[string, UpdateContactInput, (string | undefined)?]>()
    expectTypeOf<Parameters<CrmApi['createLead']>>().toEqualTypeOf<[CreateLeadInput]>()
    expectTypeOf<Parameters<CrmApi['updateLead']>>().toEqualTypeOf<[string, UpdateLeadInput, (string | undefined)?]>()
    expectTypeOf<Parameters<CrmApi['createStakeholder']>>().toEqualTypeOf<[CreateStakeholderInput]>()
    expectTypeOf<Parameters<CrmApi['updateStakeholder']>>().toEqualTypeOf<[string, UpdateStakeholderInput, (string | undefined)?]>()
  })

  it('targets Opportunity relation updates through separate method parameters', () => {
    expectTypeOf<Parameters<CrmApi['createOpportunityStakeholder']>>()
      .toEqualTypeOf<[string, CreateOpportunityStakeholderInput]>()
    expectTypeOf<Parameters<CrmApi['updateOpportunityStakeholder']>>()
      .toEqualTypeOf<[string, string, UpdateOpportunityStakeholderInput]>()
    expectTypeOf<Parameters<CrmApi['createOpportunityAction']>>()
      .toEqualTypeOf<[string, CreateOpportunityActionInput]>()
    expectTypeOf<Parameters<CrmApi['updateOpportunityAction']>>()
      .toEqualTypeOf<[string, string, UpdateOpportunityActionInput]>()
    expectTypeOf<Parameters<CrmApi['addEvaluationRun']>>()
      .toEqualTypeOf<[string, AddEvaluationRunInput]>()
  })
})
