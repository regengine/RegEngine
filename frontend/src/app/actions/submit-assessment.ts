'use server';

import { createSupabaseServerClient } from '@/lib/supabase/server';

export interface AssessmentFormData {
  name: string;
  email: string;
  company: string;
  role: string;
  facilityCount: string;
  phone?: string;
  quizScore?: number;
  quizGrade?: string;
  quizAnswers?: Record<string, any>;
  source?: string;
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
      return {
        success: true, // Don't reveal duplicate to user
      };
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
        quiz_score: data.quizScore ?? null,
        quiz_grade: data.quizGrade ?? null,
        quiz_answers: data.quizAnswers ?? null,
        source: data.source || 'recall-readiness',
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
