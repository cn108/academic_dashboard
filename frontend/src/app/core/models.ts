export type Role = 'student' | 'teacher';
export type PublishStatus = 'draft' | 'published' | 'archived';

export interface Me {
  id: number;
  username: string;
  name: string;
  email: string;
  role: Role;
  is_staff: boolean;
  admission_number: string | null;
  gender: string;
  school_class: number | null;
  class_name: string | null;
  must_change_password: boolean;
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface Paged<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AcademicSession {
  id: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
}

export interface Term {
  id: number;
  session: number;
  session_name: string;
  name: string;
  display_name: string;
  is_current: boolean;
}

export interface CurrentTerm {
  term: Term;
  session: AcademicSession;
}

export interface StudentSummary {
  id: number;
  username: string;
  full_name: string;
  admission_number: string | null;
  gender: string;
}

export interface SchoolClass {
  id: number;
  name: string;
  level: string;
  class_teacher: number | null;
  class_teacher_name: string | null;
  capacity: number;
  student_count: number;
  students_detail: StudentSummary[];
  created_at: string;
}

export interface Subject {
  id: number;
  name: string;
  school_class: number;
  class_name: string;
  teacher: number | null;
  teacher_name: string | null;
}

export interface Result {
  id: number;
  student: number;
  student_name: string;
  admission_number: string | null;
  subject: number;
  subject_name: string;
  school_class: number;
  class_name: string;
  session: number;
  session_name: string;
  term: number;
  term_name: string;
  ca1: number;
  ca2: number;
  ca3: number;
  ca_total: number;
  exam: number;
  total: number;
  grade: string;
  remarks: string;
  status: PublishStatus;
  published_at: string | null;
  updated_at: string;
}

export interface LessonNote {
  id: number;
  subject: number;
  subject_name: string;
  school_class: number;
  class_name: string;
  term: number | null;
  term_name: string | null;
  week_number: number;
  topic: string;
  content: string;
  attachment: string | null;
  status: PublishStatus;
  published_at: string | null;
  created_at: string;
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  school_class: number | null;
  class_name: string | null;
  audience: string;
  author: string | null;
  status: PublishStatus;
  published_at: string | null;
  created_at: string;
}

export interface Assignment {
  id: number;
  title: string;
  due_date: string;
  kind: string;
  subject: number | null;
  subject_name: string | null;
  school_class: number | null;
  class_name: string | null;
  term: number | null;
  term_name: string | null;
  marks_total: string;
  status: PublishStatus;
  published_at: string | null;
  is_overdue: boolean;
  submissions_count: number;
  created_at: string;
}

export interface Submission {
  id: number;
  assignment: number;
  assignment_title: string;
  class_name: string | null;
  student: number;
  student_name: string;
  file: string;
  note: string;
  submitted_at: string;
  marks: string | null;
  feedback: string;
  is_graded: boolean;
}

export interface AttendanceRecord {
  id: number;
  school_class: number;
  class_name: string;
  student: number;
  student_name: string;
  date: string;
  status: 'present' | 'late' | 'absent';
}

export interface AttendanceSummary {
  school_class: number;
  class_name: string;
  present: number;
  late: number;
  absent: number;
}

export interface BroadsheetSubject {
  id: number;
  name: string;
  teacher: number | null;
  class_average: number | null;
  results_count: number;
}

export interface BroadsheetScore {
  subject: number;
  subject_name: string;
  ca1: number;
  ca2: number;
  ca3: number;
  exam: number;
  total: number;
  grade: string;
  remarks: string;
  teacher_remark: string;
}

export interface BroadsheetStudent {
  id: number;
  full_name: string;
  admission_number: string | null;
  scores: BroadsheetScore[];
  subjects_count: number;
  total: number;
  average: number | null;
  position: number | null;
}

export interface Broadsheet {
  class: { id: number; name: string; level: string };
  session: { id: number; name: string };
  term: { id: number; name: string; session_name: string };
  subjects: BroadsheetSubject[];
  students: BroadsheetStudent[];
  student_count: number;
}

export interface ResultImportReport {
  class: { id: number; name: string };
  session: { id: number; name: string };
  term: { id: number; name: string };
  created: number;
  updated: number;
  errors: { row: number; reason: string }[];
  total_rows: number;
}

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'];

/** A readable message when a chosen file is not allowed, otherwise null. */
export function uploadProblem(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension)) {
    return 'Upload a PDF, Word document or image (PDF, DOC, DOCX, PNG, JPG).';
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return 'That file is larger than 5 MB. Compress it or upload a smaller copy.';
  }
  return null;
}

export interface StudentImportResult {
  created: string[];
  created_count: number;
  skipped: { admission_number: string; reason: string }[];
  skipped_count: number;
  class: SchoolClass;
  default_password: string;
}

export const KIND_LABELS: Record<string, string> = {
  assignment: 'Assignment',
  coursework: 'Coursework',
  group_project: 'Group project',
};

export function gradeTone(grade: string): string {
  if (grade === 'A' || grade === 'B') {
    return 'badge-success';
  }
  if (grade === 'C') {
    return 'badge-info';
  }
  if (grade === 'D' || grade === 'E') {
    return 'badge-warning';
  }
  return 'badge-danger';
}

export function statusTone(status: PublishStatus): string {
  if (status === 'published') {
    return 'badge-success';
  }
  if (status === 'archived') {
    return 'badge-danger';
  }
  return 'badge-warning';
}
