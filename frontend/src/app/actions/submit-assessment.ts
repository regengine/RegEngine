'use server';

import { createSupabaseServerClient } from '@/lib/supabase/server';
import { isValidEmail } from '@/lib/validation';

export interface AssessmentFormData {
  // Required — gate fields
  name: string;
  email: string;
  company: string;
  role: string;
  // Enrichment — optional second step
  facilityCount?: string;
  phone?: string;
  annualRevenue?: string;
  currentSystem?: string;
  biggestRetailer?: string;
  complianceDeadline?: string;
  recentFdaInspection?: string;
  productCategories?: string;
  // Tool context — captured passively
  quizScore?: number;
  quizGrade?: string;
  quizAnswers?: Record<string, unknown>;
  source?: string;  toolInputs?: Record<string, unknown>;
  utmSource?: string;
  utmMedium?: string;
  utmCampaign?: string;
  referrer?: string;
}

export interface AssessmentResult {
  success: boolean;
  error?: string;
}

export async function submitAssessment(
  data: AssessmentFormData
): Promise<AssessmentResult> {
  try {
    // Validate required fields
    if (!data.name || !data.email || !data.company) {
      return { success: false, error: 'Name, email, and company are required.' };
    }

    if (!isValidEmail(data.email)) {
      return { success: false, error: 'Please enter a valid email address.' };
    }

    const supabase = await createSupabaseServerClient();

    // Dedupe-by-email and enrichment run inside submit_assessment_lead(), a
    // SECURITY DEFINER function: the anon/authenticated roles hold INSERT and
    // nothing else on assessment_submissions, so they cannot read or modify
    // leads directly. The function returns void — it is a write-only door.
    const { error } = await supabase.rpc('submit_assessment_lead', {
      payload: {
        name: data.name.trim(),
        email: data.email.toLowerCase().trim(),
        company: data.company.trim(),
        role: data.role || null,
        facility_count: data.facilityCount || null,
        phone: data.phone?.trim() || null,
        annual_revenue: data.annualRevenue || null,
        current_system: data.currentSystem || null,
        biggest_retailer: data.biggestRetailer || null,
        compliance_deadline: data.complianceDeadline || null,
        recent_fda_inspection: data.recentFdaInspection || null,
        product_categories: data.productCategories || null,
        quiz_score: data.quizScore ?? null,
        quiz_grade: data.quizGrade ?? null,
        quiz_answers: data.quizAnswers ?? null,
        tool_inputs: data.toolInputs ?? null,
        source: data.source || 'unknown',
        utm_source: data.utmSource || null,
        utm_medium: data.utmMedium || null,
        utm_campaign: data.utmCampaign || null,
        referrer: data.referrer || null,
      },
    });

    if (error) {
      console.error('Assessment submission error:', error);
      return { success: false, error: 'Something went wrong. Please try again.' };
    }

    return { success: true };
  } catch (err) {
    console.error('Assessment submission exception:', err);
    return { success: false, error: 'Something went wrong. Please try again.' };
  }
}
