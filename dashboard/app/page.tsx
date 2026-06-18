'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';

/* ── Types ── */
type StageId = 'drive_extract' | 'llm_analysis' | 'report_service' | 'email';
type StageStatus = 'pending' | 'running' | 'completed' | 'error';

interface OutputFile {
  name: string;
  exists: boolean;
  size: number;
}

interface PipelineEvent {
  stage: StageId | 'pipeline';
  status: StageStatus | 'success' | 'failed';
  message?: string;
  html?: string;
  output_files?: OutputFile[];
}

interface AppSettings {
  recipients: string[];
  next_run: string;
  stop_run: string;
  continuous: boolean;
  active: boolean;
  subject: string;
  body_line: string;
  interval_hours: number;
  cron_expression: string;
  last_run: string | null;
}

const AVAILABLE_EMAILS = [
  'aryan.gupta@wohlig.com',
  'chirag@wohlig.com',
  'jagruti@wohlig.com',
  'dhruv.solanki@wohlig.com',
  'chintan@wohlig.com',
  'ankit.shrivastav@wohlig.com',
];

/* ── Helpers ── */
const fmtDate = (d?: string | null) => {
  if (!d) return 'Not scheduled';
  const date = new Date(d);
  if (isNaN(date.getTime())) return 'Not scheduled';
  const opts: Intl.DateTimeFormatOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
  const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local';
  return `${date.toLocaleDateString(undefined, opts)} at ${time} ${tz}`;
};

const fmtLastRun = (d?: string | null) => {
  if (!d) return 'No runs yet';
  const date = new Date(d);
  if (isNaN(date.getTime())) return 'No runs yet';
  const opts: Intl.DateTimeFormatOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false };
  return date.toLocaleString(undefined, opts);
};

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

/* ── Main Page ── */
export default function HomePage() {
  const [html, setHtml] = useState<string>('');
  const [reportOnlyLoading, setReportOnlyLoading] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [activeTab, setActiveTab] = useState<'preview' | 'source'>('preview');
  const [status, setStatus] = useState<{ text: string; type: 'ok' | 'err' | '' }>({ text: 'Ready', type: '' });

  const [outputFiles, setOutputFiles] = useState<Record<StageId, OutputFile[]>>({
    drive_extract: [],
    llm_analysis: [],
    report_service: [],
    email: [],
  });

  const [stages, setStages] = useState<Record<StageId, { status: StageStatus; log: string }>>({
    drive_extract: { status: 'pending', log: 'Waiting...' },
    llm_analysis: { status: 'pending', log: 'Waiting...' },
    report_service: { status: 'pending', log: 'Waiting...' },
    email: { status: 'pending', log: 'Waiting...' },
  });

  const STAGE_ORDER: StageId[] = ['drive_extract', 'llm_analysis', 'report_service', 'email'];

  /* Mark all stages before the current one as completed */
  const completeEarlierStages = useCallback((currentStage: StageId) => {
    const idx = STAGE_ORDER.indexOf(currentStage);
    if (idx <= 0) return;
    setStages(prev => {
      const next = { ...prev };
      STAGE_ORDER.slice(0, idx).forEach(sid => {
        if (next[sid].status === 'running' || next[sid].status === 'pending') {
          next[sid] = { ...next[sid], status: 'completed', log: next[sid].log || 'Done' };
        }
      });
      return next;
    });
  }, []);
  const [pipelineOpen, setPipelineOpen] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState('Ready to start...');
  const [pipelineState, setPipelineState] = useState<'idle' | 'success' | 'error'>('idle');
  const [isReportOnlyMode, setIsReportOnlyMode] = useState(false);

  const [settings, setSettings] = useState<AppSettings>({
    recipients: ['chintan@wohlig.com', 'jagruti@wohlig.com', 'chirag@wohlig.com'],
    next_run: '',
    stop_run: '',
    continuous: false,
    active: false,
    subject: 'Company Workforce Report',
    body_line: 'Dear Team,\n\nPlease find the attached Company Workforce Report for your review.\n\nThis report summarizes the current workforce status, project allocations, and resource utilization across the organization.\n\nRegards,\n\nDhruv Solanki\nAryan Gupta',
    interval_hours: 24,
    cron_expression: '',
    last_run: null,
  });

  /* ── Fetch existing report on mount ── */
  useEffect(() => {
    fetch('/api/report')
      .then(r => r.json())
      .then(d => {
        if (d.html) {
          setHtml(d.html);
          setStatus({ text: 'Loaded existing report', type: 'ok' });
        }
      })
      .catch(() => {});
  }, []);

  /* ── Fetch settings on mount ── */
  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(d => {
        if (d) setSettings(prev => ({ ...prev, ...d }));
      })
      .catch(() => {});
  }, []);

  /* ── Persist draft next_run in localStorage ── */
  useEffect(() => {
    const saved = localStorage.getItem('nextRunDraft');
    if (saved) {
      setSettings(prev => ({ ...prev, next_run: saved }));
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('nextRunDraft', settings.next_run);
  }, [settings.next_run]);

  /* ── Run Pipeline Only (no email) ── */
  const runPipelineOnly = useCallback(async () => {
    // Confirm the FastAPI backend is reachable before opening the overlay.
    try {
      const probe = await fetch('/api/health', { method: 'GET' });
      if (!probe.ok) throw new Error(`Backend health returned ${probe.status}`);
    } catch (err: any) {
      setPipelineOpen(true);
      setPipelineState('error');
      setPipelineMsg('Backend not running. In a separate terminal run: python -m uvicorn api.main:app --host 127.0.0.1 --port 8000');
      setStatus({ text: 'Backend not running', type: 'err' });
      return;
    }

    setReportOnlyLoading(true);
    setIsReportOnlyMode(true);
    setPipelineOpen(true);
    setPipelineState('idle');
    setPipelineMsg('Checking existing stage outputs...');
    setOutputFiles({ drive_extract: [], llm_analysis: [], report_service: [], email: [] });

    // ── 1. Check disk state first ───────────────────────────────────────
    let initialStages: Record<StageId, { status: StageStatus; log: string }> = {
      drive_extract: { status: 'pending', log: 'Waiting...' },
      llm_analysis: { status: 'pending', log: 'Waiting...' },
      report_service: { status: 'pending', log: 'Waiting...' },
      email: { status: 'pending', log: 'Skipped — report only mode' },
    };
    let initialFiles: Record<StageId, OutputFile[]> = {
      drive_extract: [], llm_analysis: [], report_service: [], email: [],
    };

    let driveExists = false;
    let llmExists = false;
    try {
      const res = await fetch('/api/pipeline-status');
      if (res.ok) {
        const diskState = await res.json();

        if (diskState.drive_extract?.completed) {
          driveExists = true;
          initialStages.drive_extract = { status: 'completed', log: 'Already complete ✓ (from previous run)' };
          initialFiles.drive_extract = diskState.drive_extract.output_files || [];
        }
        if (diskState.llm_analysis?.completed) {
          llmExists = true;
          initialStages.llm_analysis = { status: 'completed', log: 'Already complete ✓ (from previous run)' };
          initialFiles.llm_analysis = diskState.llm_analysis.output_files || [];
        }
        if (diskState.report_service?.completed) {
          initialStages.report_service = { status: 'completed', log: 'Already complete ✓ (from previous run)' };
          initialFiles.report_service = diskState.report_service.output_files || [];
        }
      }
    } catch { /* ignore */ }

    setStages(initialStages);
    setOutputFiles(initialFiles);

    // Decide which endpoint to call:
    //   - /api/generate-report  → skips Drive + LLM, runs only report_service
    //   - /api/run-pipeline     → runs everything
    const endpoint = driveExists && llmExists ? '/api/generate-report' : '/api/run-pipeline';
    if (endpoint === '/api/generate-report') {
      setPipelineMsg('Drive + LLM outputs already exist. Skipping to report generation...');
    } else {
      setPipelineMsg('Starting pipeline...');
    }

    try {
      const initRes = await fetch(endpoint, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({}),
      });
      if (!initRes.ok) throw new Error(`Failed to start pipeline: ${initRes.status}`);
      const initData = await initRes.json();
      if (!initData.job_id) throw new Error('No job_id returned');

      const res = await fetch(`/api/jobs/${initData.job_id}/stream`, {
        method: 'GET',
        headers: { 
          'Accept': 'text/event-stream'
        }
      });
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (reader) {
        const { done, value } = await reader.read();
        if (done) {
          const tail = decoder.decode();
          if (tail) buf += tail;
          break;
        }
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.trim() || !line.startsWith('data: ')) continue;
          const dataStr = line.slice(6);
          if (!dataStr) continue;
          try {
            const data: PipelineEvent = JSON.parse(dataStr);
            if (data.stage === 'pipeline') {
              if (data.status === 'success') {
                setPipelineState('success');
                setPipelineMsg('Report generated successfully!');
                setHtml(data.html ?? '');
                setStatus({ text: 'Report generated successfully', type: 'ok' });
                setSettings(prev => ({ ...prev, last_run: new Date().toISOString() }));
                setStages(prev => ({
                  ...prev,
                  report_service: { ...prev.report_service, status: 'completed', log: prev.report_service.log || 'Report generated' },
                }));
                setTimeout(() => setPipelineOpen(false), 1200);
              } else if (data.status === 'failed' || data.status === 'error') {
                setPipelineState('error');
                setPipelineMsg(`Failed: ${data.message || 'Unknown error'}`);
                setStatus({ text: `Pipeline failed: ${data.message || ''}`, type: 'err' });
              } else if (data.status === 'started') {
                setPipelineState('running');
                setPipelineMsg(data.message || 'Pipeline started');
              }

            } else {
              const sid = data.stage as StageId;
              completeEarlierStages(sid);
              setStages(prev => {
                const currentLog = prev[sid].log || '';
                const nextLog = data.status === 'running'
                  ? (currentLog === 'Waiting...' ? (data.message || '') : `${currentLog}\n${data.message || ''}`)
                  : (data.message || prev[sid].log || '');
                return {
                  ...prev,
                  [sid]: { status: data.status as StageStatus, log: nextLog },
                };
              });
              if (data.output_files) {
                setOutputFiles(prev => ({ ...prev, [sid]: data.output_files! }));
              }
              if (data.status === 'running') {
                setPipelineMsg(`${sid}: ${data.message || 'Running...'}`);
              } else if (data.status === 'completed') {
                setPipelineMsg(`${sid} completed`);
              }
            }
          } catch {
            // ignore parse errors
          }
        }
      }

      if (buf.trim()) {
        const remainingLines = buf.split('\n');
        for (const line of remainingLines) {
          if (!line.trim() || !line.startsWith('data: ')) continue;
          const dataStr = line.slice(6);
          if (!dataStr) continue;
          try {
            const data: PipelineEvent = JSON.parse(dataStr);
            if (data.stage === 'pipeline') {
              if (data.status === 'success') {
                setPipelineState('success');
                setPipelineMsg('Report generated successfully!');
                setHtml(data.html ?? '');
                setStatus({ text: 'Report generated successfully', type: 'ok' });
                setSettings(prev => ({ ...prev, last_run: new Date().toISOString() }));
                setStages(prev => ({
                  ...prev,
                  report_service: { ...prev.report_service, status: 'completed', log: prev.report_service.log || 'Report generated' },
                }));
                setTimeout(() => setPipelineOpen(false), 1200);
              } else {
                setPipelineState('error');
                setPipelineMsg(`Failed: ${data.message || 'Unknown error'}`);
                setStatus({ text: `Pipeline failed: ${data.message || ''}`, type: 'err' });
              }
            } else {
              const sid = data.stage as StageId;
              completeEarlierStages(sid);
              setStages(prev => {
                const currentLog = prev[sid].log || '';
                const nextLog = data.status === 'running'
                  ? (currentLog === 'Waiting...' ? (data.message || '') : `${currentLog}\n${data.message || ''}`)
                  : (data.message || prev[sid].log || '');
                return {
                  ...prev,
                  [sid]: { status: data.status as StageStatus, log: nextLog },
                };
              });
              if (data.output_files) {
                setOutputFiles(prev => ({ ...prev, [sid]: data.output_files! }));
              }
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      setPipelineState('error');
      setPipelineMsg(err?.message?.includes('Failed to fetch') ? 'Backend not running' : `Error: ${err.message}`);
      setStatus({ text: 'Backend not running or unreachable', type: 'err' });
    } finally {
      setReportOnlyLoading(false);
    }
  }, []);
  const sendEmail = useCallback(async () => {
    if (!settings.recipients.length) {
      setStatus({ text: 'No recipients selected', type: 'err' });
      return;
    }
    setEmailSending(true);
    try {
      const res = await fetch('/api/send-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipients: settings.recipients,
          subject: settings.subject,
          body_line: settings.body_line,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setStatus({ text: `Email sent to ${data.sent_to?.join(', ')}`, type: 'ok' });
      } else {
        setStatus({ text: `Email failed: ${data.error || data.detail || ''}`, type: 'err' });
      }
    } catch (err: any) {
      setStatus({ text: `Email failed: ${err.message}`, type: 'err' });
    } finally {
      setEmailSending(false);
    }
  }, [settings]);

  /* ── Save Settings ── */
  const saveSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Server returned ${res.status}: ${errText.substring(0, 100)}`);
      }
      const data = await res.json();
      if (data.settings) setSettings(prev => ({ ...prev, ...data.settings }));
      setShowSettings(false);
      const active = data.settings?.active ?? settings.active;
      const nextRunText = settings.next_run ? fmtDate(settings.next_run) : 'no next run set';
      setStatus({
        text: active
          ? `Automation ACTIVE — next run: ${nextRunText}`
          : 'Automation INACTIVE — settings saved',
        type: 'ok',
      });
    } catch (err: any) {
      setStatus({ text: `Save failed: ${err.message}`, type: 'err' });
    }
  }, [settings]);

  const resetSettings = useCallback(() => {
    setSettings({
      recipients: [],
      next_run: '',
      stop_run: '',
      continuous: false,
      active: false,
      subject: 'Company report',
      body_line: 'Please find the attached company workforce report.',
      interval_hours: 24,
      cron_expression: '',
      last_run: settings.last_run,
    });
  }, [settings.last_run]);

  /* ── Toggle recipient ── */
  const toggleRecipient = useCallback((email: string) => {
    setSettings(prev => {
      const exists = prev.recipients.includes(email);
      return {
        ...prev,
        recipients: exists ? prev.recipients.filter(e => e !== email) : [...prev.recipients, email],
      };
    });
  }, []);

  /* ── Derived states ── */

  const iframeSrc = useMemo(() => {
    if (!html) return '';
    const blob = new Blob([html], { type: 'text/html' });
    return URL.createObjectURL(blob);
  }, [html]);

  /* ── Render ── */
  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 flex items-center justify-between gap-4 px-6 py-3 bg-navy text-white border-b border-hairline/40">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-br from-mist to-orchid rounded-lg px-3 py-1.5 border border-hairline shadow-sm flex items-center justify-center">
            <Image src="/logo.webp" alt="Wohlig Logo" width={80} height={24} className="object-contain" priority />
          </div>
          <span className="text-sm font-medium text-white/80 hidden sm:inline">Report Dashboard</span>
          {settings.active && (
            <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Automation active
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Generate Report Once — pipeline only, no email */}
          <button
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-white/10 hover:bg-white/20 text-white transition ${reportOnlyLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
            onClick={() => { if (!reportOnlyLoading) runPipelineOnly(); }}
            disabled={reportOnlyLoading}
          >
            {reportOnlyLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Running…
              </>
            ) : 'Generate Report Only'}
          </button>

          {/* Send Email only */}
          <button
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition ${
              settings.recipients.length && !emailSending
                ? 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-md'
                : 'bg-white/10 text-white/40 cursor-not-allowed'
            }`}
            onClick={sendEmail}
            disabled={!settings.recipients.length || emailSending}
          >
            {emailSending ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Sending…
              </>
            ) : (
              <>📧 Send Email</>
            )}
          </button>

          <button
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-white/10 hover:bg-white/20 text-white transition"
            onClick={() => setShowSettings(s => !s)}
          >
            ⚙️ Settings
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col gap-4 p-5 max-w-[1400px] mx-auto w-full">
        {/* Status bar */}
        <div className="flex items-center gap-3 px-4 py-2.5 bg-white border border-hairline rounded-xl shadow-sm text-sm text-slate">
          <span className={`w-2.5 h-2.5 rounded-full ${status.type === 'ok' ? 'bg-success' : status.type === 'err' ? 'bg-danger' : 'bg-slate'}`} />
          <span>{status.text}</span>
          {settings.last_run && (
            <span className="ml-auto text-xs text-slate/70">Last run: {fmtLastRun(settings.last_run)}</span>
          )}
        </div>

        {/* Viewer */}
        <div className="relative flex-1 bg-white border border-hairline rounded-xl overflow-hidden shadow-sm flex flex-col min-h-[60vh]">
          <div className="flex border-b border-hairline bg-mist">
            {(['preview', 'source'] as const).map(tab => (
              <button
                key={tab}
                className={`px-5 py-3 text-sm font-semibold border-b-2 transition ${
                  activeTab === tab
                    ? 'text-indigo border-indigo bg-indigo/[0.06]'
                    : 'text-slate border-transparent hover:text-indigo hover:bg-indigo/[0.04]'
                }`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'preview' ? 'Preview' : 'Source'}
              </button>
            ))}
          </div>

          <div className="flex-1 relative bg-light overflow-hidden">
            {activeTab === 'preview' ? (
              html ? (
                <iframe
                  src={iframeSrc}
                  className="absolute inset-0 w-full h-full border-none"
                  sandbox="allow-scripts allow-same-origin"
                />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-slate text-sm gap-2">
                  <p>Click <span className="font-semibold text-indigo">Generate Report Only</span> to create the report.</p>
                  <p className="text-xs opacity-70">Use Settings to enable automatic scheduled emails.</p>
                </div>
              )
            ) : (
              <pre className="absolute inset-0 w-full h-full p-5 text-xs leading-relaxed text-slate whitespace-pre-wrap break-words font-mono bg-white overflow-auto">
                {html || 'No HTML generated yet.'}
              </pre>
            )}
          </div>

          {/* Pipeline overlay */}
          {pipelineOpen && (
            <div className="absolute inset-0 bg-white/97 backdrop-blur-sm flex flex-col p-8 gap-6 overflow-y-auto z-20">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-navy">Pipeline Progress</h2>
                <button className="text-sm text-slate hover:text-indigo px-3 py-1 rounded-lg hover:bg-mist transition" onClick={() => setPipelineOpen(false)}>
                  ✕ Close
                </button>
              </div>

              <div className="flex flex-col gap-3">
                {([
                  { id: 'drive_extract' as StageId, num: 1, name: 'Fetch Excel from Google Drive', desc: 'Download and extract all sheet data' },
                  { id: 'llm_analysis' as StageId, num: 2, name: 'LLM Analysis', desc: 'Send data to Ollama for workforce audit' },
                  { id: 'report_service' as StageId, num: 3, name: 'Generate HTML Report', desc: 'Render the final workforce report from template' },
                  { id: 'email' as StageId, num: 4, name: 'Schedule Email', desc: 'Schedule email to selected recipients at configured date/time' },
                ]).filter(s => !(isReportOnlyMode && s.id === 'email')).map(s => {
                  const st = stages[s.id];
                  const files = outputFiles[s.id] || [];
                  const isCompleted = st.status === 'completed';
                  const isRunning = st.status === 'running';
                  const isError = st.status === 'error';
                  return (
                    <div
                      key={s.id}
                      className={`flex items-start gap-4 p-4 rounded-xl border-2 transition-all duration-300 ${
                        isRunning
                          ? 'border-purple-400 bg-gradient-to-br from-violet-50 to-purple-100 shadow-lg shadow-purple-200/50 transform scale-[1.01]'
                          : isCompleted
                          ? 'border-purple-600 bg-gradient-to-br from-purple-50 to-fuchsia-50'
                          : isError
                          ? 'border-red-500 bg-red-50'
                          : 'border-purple-200/60 bg-purple-50/30'
                      }`}
                    >
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 border transition-all ${
                          isRunning
                            ? 'bg-gradient-to-br from-purple-600 to-violet-500 text-white border-transparent animate-pulse shadow-lg shadow-purple-500/30'
                            : isCompleted
                            ? 'bg-purple-600 text-white border-transparent'
                            : isError
                            ? 'bg-red-500 text-white border-transparent'
                            : 'bg-purple-100 text-purple-300 border-purple-200'
                        }`}
                      >
                        {isCompleted ? '✓' : isError ? '✕' : s.num}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-bold text-sm text-navy">{s.name}</div>
                        <div className="text-xs text-slate mt-0.5">{s.desc}</div>
                        <div className="mt-2 p-2 bg-white/70 rounded-lg text-xs font-mono text-slate max-h-28 overflow-y-auto whitespace-pre-wrap leading-relaxed border border-purple-100/50">
                          {st.log}
                        </div>
                        {files.length > 0 && (
                          <div className="mt-2 flex flex-col gap-1">
                            {files.map(f => (
                              <div key={f.name} className="flex items-center gap-2 text-[11px]">
                                <span className={f.exists ? 'text-emerald-500' : 'text-red-500'}>
                                  {f.exists ? '✓' : '✕'}
                                </span>
                                <span className="text-purple-800 font-medium truncate" title={f.name}>
                                  {f.name}
                                </span>
                                {f.exists && (
                                  <span className="text-purple-400 ml-auto shrink-0">{formatBytes(f.size)}</span>
                                )}
                                {!f.exists && (
                                  <span className="text-red-400 ml-auto shrink-0">Not found</span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-center gap-3 pt-4 border-t border-hairline">
                <div className="w-4 h-4 border-2 border-hairline border-t-indigo rounded-full animate-spin" />
                <span className={`text-sm font-semibold ${pipelineState === 'error' ? 'text-danger' : pipelineState === 'success' ? 'text-success' : 'text-indigo'}`}>
                  {pipelineMsg}
                </span>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Settings panel */}
      {showSettings && (
        <div
          className="fixed inset-0 z-[100] flex justify-end"
          onClick={e => {
            if (e.currentTarget === e.target) setShowSettings(false);
          }}
        >
          <aside className="w-[420px] max-w-full bg-white border-l border-hairline shadow-2xl flex flex-col h-full">
            <div className="flex items-center justify-between px-5 py-4 bg-mist border-b border-hairline">
              <span className="font-bold text-navy">Settings</span>
              <button className="text-sm text-slate hover:text-indigo px-3 py-1 rounded-lg hover:bg-white transition" onClick={() => setShowSettings(false)}>
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {/* Status */}
              <div className="space-y-3">
                <h3 className="text-[11px] font-bold text-indigo uppercase tracking-wider">Status</h3>
                <button
                  onClick={() => setSettings(prev => ({ ...prev, active: !prev.active }))}
                  className={`w-full flex items-center justify-between rounded-xl p-4 border transition ${
                    settings.active
                      ? 'bg-success/[0.06] border-success/30 hover:border-success'
                      : 'bg-white border-hairline hover:border-indigo'
                  }`}
                >
                  <span className="font-bold text-navy text-sm">Automation</span>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold transition ${settings.active ? 'bg-success/10 text-success' : 'bg-slate/10 text-slate'}`}>
                    {settings.active ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </button>
                <p className="text-xs text-slate opacity-70">
                  {settings.active
                    ? `Automation is ACTIVE. The scheduler will keep running across page refreshes until you open Settings and set it to INACTIVE.`
                    : `Automation is INACTIVE. Turn it ON and click Save to start scheduled runs. The state is saved on the server, so it survives refreshes and crashes.`}
                </p>
              </div>

              {/* Schedule */}
              <div className="space-y-3">
                <h3 className="text-[11px] font-bold text-indigo uppercase tracking-wider">Schedule</h3>
                
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate">Next run</label>
                  <input
                    type="datetime-local"
                    value={settings.next_run}
                    onChange={e => setSettings(prev => ({ ...prev, next_run: e.target.value }))}
                    className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition"
                  />
                </div>
                
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate">Stop run</label>
                  <input
                    type="datetime-local"
                    value={settings.stop_run}
                    onChange={e => setSettings(prev => ({ ...prev, stop_run: e.target.value }))}
                    className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition"
                  />
                </div>

                <div className="pt-2">
                  <button
                    className={`w-full py-2.5 rounded-xl text-sm font-semibold border transition ${
                      settings.continuous
                        ? 'bg-gradient-to-r from-indigo to-purple text-white border-transparent shadow-md'
                        : 'bg-white text-slate border-hairline hover:border-indigo hover:text-indigo'
                    }`}
                    onClick={() => setSettings(prev => ({ ...prev, continuous: !prev.continuous }))}
                  >
                    🔁 Continuous Mode
                  </button>
                </div>

                {settings.continuous && (
                  <div className="space-y-3 pt-2">
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate">Interval (hours)</label>
                      <input
                        type="number"
                        min={1}
                        value={settings.interval_hours}
                        onChange={e => setSettings(prev => ({ ...prev, interval_hours: Number(e.target.value) }))}
                        className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate">Or Cron Expression</label>
                      <input
                        type="text"
                        placeholder="e.g. 0 9 * * *"
                        value={settings.cron_expression}
                        onChange={e => setSettings(prev => ({ ...prev, cron_expression: e.target.value }))}
                        className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition font-mono"
                      />
                      <p className="text-xs text-slate opacity-70">Takes precedence over interval if set.</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Recipients */}
              <div className="space-y-3">
                <h3 className="text-[11px] font-bold text-indigo uppercase tracking-wider">Recipients</h3>
                <div className="grid grid-cols-1 gap-2">
                  {AVAILABLE_EMAILS.map(email => (
                    <button
                      key={email}
                      onClick={() => toggleRecipient(email)}
                      className={`px-4 py-2.5 rounded-xl text-sm font-semibold border transition text-center ${
                        settings.recipients.includes(email)
                          ? 'bg-gradient-to-r from-indigo to-purple text-white border-transparent shadow-md'
                          : 'bg-white text-slate border-hairline hover:border-indigo hover:text-indigo'
                      }`}
                    >
                      {email}
                    </button>
                  ))}
                </div>
              </div>

              {/* Subject & Body */}
              <div className="space-y-3">
                <h3 className="text-[11px] font-bold text-indigo uppercase tracking-wider">Email Content</h3>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate">Subject</label>
                  <input
                    value={settings.subject}
                    onChange={e => setSettings(prev => ({ ...prev, subject: e.target.value }))}
                    className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate">Body line</label>
                  <textarea
                    rows={2}
                    value={settings.body_line}
                    onChange={e => setSettings(prev => ({ ...prev, body_line: e.target.value }))}
                    className="w-full bg-mist border border-hairline rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo focus:ring-2 focus:ring-indigo/10 transition resize-none"
                  />
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-4 bg-mist border-t border-hairline flex items-center justify-between">
              <button
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-white border border-hairline hover:bg-white/80 text-slate transition"
                onClick={resetSettings}
              >
                Reset
              </button>
              <button
                className="px-5 py-2 rounded-xl text-sm font-semibold bg-emerald-500 hover:bg-emerald-600 text-white shadow-md transition"
                onClick={saveSettings}
              >
                Save
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
