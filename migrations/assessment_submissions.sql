-- Create assessment_submissions table
CREATE TABLE assessment_submissions (
  id BIGSERIAL PRIMARY KEY,
  assessment_id BIGINT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  status VARCHAR(50) NOT NULL DEFAULT 'in_progress',
  score DECIMAL(5, 2),
  answers JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX idx_assessment_submissions_assessment_id ON assessment_submissions(assessment_id);
CREATE INDEX idx_assessment_submissions_user_id ON assessment_submissions(user_id);
CREATE INDEX idx_assessment_submissions_status ON assessment_submissions(status);
CREATE INDEX idx_assessment_submissions_created_at ON assessment_submissions(created_at);
CREATE INDEX idx_assessment_submissions_assessment_user ON assessment_submissions(assessment_id, user_id);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_assessment_submissions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_assessment_submissions_updated_at
BEFORE UPDATE ON assessment_submissions
FOR EACH ROW
EXECUTE FUNCTION update_assessment_submissions_updated_at();