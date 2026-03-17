'use server';

import { createSupabaseServerClient } from '@/lib/supabase/server';

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
  quizAnswers?: Record<string, any>;
  source?: string;
  toolInputs?: Record<string, any>;
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

    if (!data.email.includes('@') || !data.email.includes('.')) {
      return { success: false, error: 'Please enter a valid email address.' };
    }

    const supabase = await createSupabaseServerClient();

    // Check for duplicate submission (same email in last 24h)
    const twentyFourHoursAgo = new Date(
      Date.now() - 24 * 60 * 60 * 1000
    ).toISOString();

    const { data: existing } = await supabase
      .from('assessment_submissions')
      .select('id')
      .eq('email', data.email.toLowerCase().trim())
      .gte('created_at', twentyFourHoursAgo)
      .limit(1);

    if (existing && existing.length > 0) {
      // Update enrichment fields if this is a returning lead adding more info
      await supabase
        .from('assessment_submissions')
        .update({
          facility_count: data.facilityCount || undefined,
          phone: data.phone?.trim() || undefined,
          annual_revenue: data.annualRevenue || undefined,
          current_system: data.currentSystem || undefined,
          biggest_retailer: data.biggestRetailer || undefined,
          compliance_deadline: data.complianceDeadline || undefined,
          recent_fda_inspection: data.recentFdaInspection || undefined,
          product_categories: data.productCategories || undefined,
        })
        .eq('id', existing[0].id);

      return { success: true };
    }

    const { error } = await supabase
      .from('assessment_submissions')
      .insert({
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
