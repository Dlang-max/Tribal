// Render the standalone workspace shell and sample knowledge explorer pages.
import { useState, type ReactNode } from 'react';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Boxes,
  CircleHelp,
  Command,
  GitBranch,
  LayoutDashboard,
  Search,
  Settings2,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { NAVIGATION_ITEMS, type NavigationId } from '@/shared';
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from '@/components/ui';
import './app.css';

type AppProps = {
  knowledgeExplorer?: ReactNode;
};

const navIcons: Record<NavigationId, typeof LayoutDashboard> = {
  overview: LayoutDashboard,
  repositories: GitBranch,
  'agents-tasks': Bot,
  'knowledge-explorer': Workflow,
  settings: Settings2,
};

const repositories = [
  { name: 'tribal', owner: 'tribal-labs', language: 'TypeScript', updated: '12 min ago', color: 'violet' },
  { name: 'context-agent', owner: 'tribal-labs', language: 'Python', updated: 'Yesterday', color: 'blue' },
  { name: 'docs-site', owner: 'tribal-labs', language: 'MDX', updated: '3 days ago', color: 'amber' },
];

const agents = [
  { initials: 'CR', name: 'Context Refresher', role: 'Keeps repository context current', state: 'Ready', tone: 'green' },
  { initials: 'PR', name: 'Pull Request Guide', role: 'Prepares project-aware reviews', state: 'Paused', tone: 'muted' },
  { initials: 'DG', name: 'Docs Gardener', role: 'Finds gaps in project documentation', state: 'Ready', tone: 'green' },
];

const tasks = [
  { title: 'Refresh Tribal repository context', agent: 'Context Refresher', time: 'Today, 10:42 AM', state: 'Complete', tone: 'green' },
  { title: 'Review documentation changes', agent: 'Pull Request Guide', time: 'Today, 9:18 AM', state: 'Queued', tone: 'violet' },
  { title: 'Map onboarding references', agent: 'Docs Gardener', time: 'Yesterday, 4:06 PM', state: 'Complete', tone: 'green' },
];

function PageHeading({ eyebrow, title, description, action }: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-heading-action">{action}</div>}
    </div>
  );
}

function SampleTag() {
  return <span className="sample-tag"><span /> Sample data</span>;
}

function OverviewPage({ onNavigate }: { onNavigate: (id: NavigationId) => void }) {
  return (
    <>
      <PageHeading
        eyebrow="Workspace overview"
        title="Good morning, Daniel"
        description="A clear view of the context your agents can draw from."
        action={<SampleTag />}
      />

      <div className="stat-grid">
        <Card className="stat-card">
          <CardContent>
            <div className="stat-label"><span>Repositories</span><GitBranch size={16} /></div>
            <div className="stat-value">03</div>
            <div className="stat-note">Connected in this sample workspace</div>
          </CardContent>
        </Card>
        <Card className="stat-card">
          <CardContent>
            <div className="stat-label"><span>Knowledge records</span><Boxes size={16} /></div>
            <div className="stat-value">248</div>
            <div className="stat-note">Illustrative objects and events</div>
          </CardContent>
        </Card>
        <Card className="stat-card">
          <CardContent>
            <div className="stat-label"><span>Agent activity</span><Activity size={16} /></div>
            <div className="stat-value">12 <span className="stat-unit">this week</span></div>
            <div className="stat-note"><span className="trend"><ArrowUpRight size={14} /> 18%</span> from last week</div>
          </CardContent>
        </Card>
      </div>

      <div className="overview-columns">
        <Card className="content-card repository-card">
          <CardHeader className="section-card-header">
            <div><div className="section-kicker">Your sources</div><CardTitle>Repositories</CardTitle></div>
            <Button variant="ghost" size="sm" onClick={() => onNavigate('repositories')}>View all <ArrowUpRight size={15} /></Button>
          </CardHeader>
          <CardContent className="repository-list">
            {repositories.map((repo) => (
              <div className="repository-row" key={repo.name}>
                <div className={`repo-icon ${repo.color}`}><GitBranch size={17} /></div>
                <div className="repo-info"><strong>{repo.owner}/{repo.name}</strong><span>{repo.language} <i /> Updated {repo.updated}</span></div>
                <span className="repo-health"><span /> Ready</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="content-card activity-card">
          <CardHeader className="section-card-header">
            <div><div className="section-kicker">At a glance</div><CardTitle>Recent activity</CardTitle></div>
            <span className="activity-live"><span /> Local preview</span>
          </CardHeader>
          <CardContent className="activity-list">
            <div className="activity-item"><span className="activity-icon violet"><Sparkles size={16} /></span><div><strong>Context refreshed</strong><span>tribal · 12 minutes ago</span></div></div>
            <div className="activity-item"><span className="activity-icon blue"><GitBranch size={16} /></span><div><strong>Repository added</strong><span>context-agent · Yesterday</span></div></div>
            <div className="activity-item"><span className="activity-icon amber"><Bot size={16} /></span><div><strong>Agent task completed</strong><span>Docs Gardener · Yesterday</span></div></div>
            <Button className="activity-link" variant="ghost" onClick={() => onNavigate('agents-tasks')}>See agents and tasks <ArrowDownRight size={15} /></Button>
          </CardContent>
        </Card>
      </div>

      <Card className="explore-banner">
        <div className="explore-mark"><Workflow size={21} /></div>
        <div className="explore-copy"><span>Explore your project context</span><p>See how repositories, concepts, and events connect.</p></div>
        <Button onClick={() => onNavigate('knowledge-explorer')}>Open Knowledge Explorer <ArrowUpRight size={15} /></Button>
      </Card>
      <p className="sample-footnote">Illustrative workspace content for the Tribal frontend preview.</p>
    </>
  );
}

function RepositoriesPage() {
  return (
    <>
      <PageHeading eyebrow="Workspace" title="Repositories" description="Browse the project sources represented in this workspace." action={<SampleTag />} />
      <Card className="content-card table-card">
        <div className="table-toolbar"><div><strong>All repositories</strong><span>3 sample sources</span></div><Button variant="outline" disabled><GitBranch size={15} /> Connect repository</Button></div>
        <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Repository</th><th>Language</th><th>Context records</th><th>Last updated</th><th>Status</th></tr></thead><tbody>
          {repositories.map((repo, index) => <tr key={repo.name}><td><div className="table-repo"><span className={`repo-icon ${repo.color}`}><GitBranch size={16} /></span><span><strong>{repo.name}</strong><small>{repo.owner}</small></span></div></td><td>{repo.language}</td><td>{[126, 78, 44][index]}</td><td>{repo.updated}</td><td><span className="status-pill ready"><span /> Sample</span></td></tr>)}
        </tbody></table></div>
        <div className="table-caption">Repository connections are illustrative. Connecting a live provider is not available in this preview.</div>
      </Card>
    </>
  );
}

function AgentsTasksPage() {
  return (
    <>
      <PageHeading eyebrow="Workspace" title="Agents and tasks" description="A sample view of agents and the work they can take on." action={<SampleTag />} />
      <section className="section-block">
        <div className="section-heading"><div><h2>Agents</h2><p>Example agent profiles for a project workspace.</p></div><Button variant="outline" disabled><Bot size={15} /> Add agent</Button></div>
        <div className="agent-grid">{agents.map((agent) => <Card className="agent-card" key={agent.name}><CardContent><div className="agent-card-top"><div className="agent-avatar">{agent.initials}</div><span className={`status-pill ${agent.tone}`}><span /> {agent.state}</span></div><h3>{agent.name}</h3><p>{agent.role}</p><div className="agent-card-bottom"><span>Sample profile</span><Button variant="ghost" size="icon" aria-label={`More about ${agent.name}`} disabled><CircleHelp size={16} /></Button></div></CardContent></Card>)}</div>
      </section>
      <section className="section-block task-section">
        <div className="section-heading"><div><h2>Recent tasks</h2><p>Local example activity, with no live agent execution.</p></div></div>
        <Card className="content-card table-card"><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Task</th><th>Agent</th><th>Time</th><th>Status</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.title}><td><strong>{task.title}</strong></td><td>{task.agent}</td><td>{task.time}</td><td><span className={`status-pill ${task.tone}`}><span /> {task.state}</span></td></tr>)}</tbody></table></div></Card>
      </section>
    </>
  );
}

function SettingsPage() {
  return (
    <>
      <PageHeading eyebrow="Workspace" title="Settings" description="Workspace preferences and connection details." action={<SampleTag />} />
      <div className="settings-grid">
        <Card className="content-card settings-card"><CardHeader><div className="section-kicker">Workspace</div><CardTitle>Workspace details</CardTitle></CardHeader><CardContent><div className="setting-row"><span>Name</span><strong>Tribal demo workspace</strong></div><div className="setting-row"><span>Visibility</span><strong>Private preview</strong></div><div className="setting-row"><span>Data source</span><strong><span className="sample-dot" /> Sample content</strong></div></CardContent></Card>
        <Card className="content-card settings-card"><CardHeader><div className="section-kicker">Connections</div><CardTitle>Integrations</CardTitle></CardHeader><CardContent><div className="integration-empty"><div className="integration-icon"><GitBranch size={18} /></div><div><strong>No live connections</strong><p>This preview does not connect to GitHub, agents, or a knowledge service.</p></div></div><Button variant="outline" disabled>Manage integrations</Button></CardContent></Card>
      </div>
      <p className="sample-footnote">Settings shown here describe a sample workspace and are not saved.</p>
    </>
  );
}

function ExplorerPage({ knowledgeExplorer }: { knowledgeExplorer?: ReactNode }) {
  if (knowledgeExplorer) return <div className="explorer-slot">{knowledgeExplorer}</div>;
  return (
    <>
      <PageHeading eyebrow="Workspace" title="Knowledge Explorer" description="Inspect the relationships between concepts in a project." action={<SampleTag />} />
      <Card className="explorer-empty content-card"><div className="explorer-empty-icon"><Workflow size={25} /></div><h2>Project context, connected</h2><p>The graph view will appear here. This sample shell does not connect to a knowledge service.</p><div className="explorer-preview"><span className="graph-node node-one">Repository</span><span className="graph-edge edge-one" /><span className="graph-node node-two">Concept</span><span className="graph-edge edge-two" /><span className="graph-node node-three">Event</span></div><span className="explorer-caption">Illustrative graph preview</span></Card>
    </>
  );
}

function OverviewPageShell({ active, onNavigate, knowledgeExplorer }: {
  active: NavigationId;
  onNavigate: (id: NavigationId) => void;
  knowledgeExplorer?: ReactNode;
}) {
  switch (active) {
    case 'repositories': return <RepositoriesPage />;
    case 'agents-tasks': return <AgentsTasksPage />;
    case 'knowledge-explorer': return <ExplorerPage knowledgeExplorer={knowledgeExplorer} />;
    case 'settings': return <SettingsPage />;
    case 'overview': return <OverviewPage onNavigate={onNavigate} />;
  }
}

export default function App({ knowledgeExplorer }: AppProps) {
  const [activePage, setActivePage] = useState<NavigationId>('overview');
  const activeLabel = NAVIGATION_ITEMS.find((item) => item.id === activePage)?.label ?? 'Overview';

  return (
    <div className="tribal-app">
      <aside className="sidebar">
        <a className="brand-lockup" href="#overview" onClick={(event) => { event.preventDefault(); setActivePage('overview'); }} aria-label="Tribal home">
          <span className="brand-mark"><Command size={19} strokeWidth={2.2} /></span><span className="brand-name">tribal<span>.</span></span>
        </a>
        <div className="workspace-switcher"><span className="workspace-avatar">T</span><span className="workspace-label"><strong>Tribal workspace</strong><small>Personal workspace</small></span><span className="switcher-dots">···</span></div>
        <div className="nav-caption">Workspace</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {NAVIGATION_ITEMS.map((item) => {
            const Icon = navIcons[item.id];
            return <button key={item.id} type="button" className={`nav-item${activePage === item.id ? ' active' : ''}`} aria-label={item.label} aria-current={activePage === item.id ? 'page' : undefined} onClick={() => setActivePage(item.id)}><Icon size={17} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'repositories' && <span className="nav-count">3</span>}</button>;
          })}
        </nav>
        <div className="sidebar-bottom"><div className="help-panel"><span className="help-icon"><CircleHelp size={16} /></span><div><strong>Need a hand?</strong><span>Explore the Tribal guide</span></div><ArrowUpRight size={14} /></div><div className="profile-row"><span className="profile-avatar">DL</span><span className="profile-name"><strong>Daniel Lang</strong><small>Workspace owner</small></span><span className="profile-menu">···</span></div></div>
      </aside>
      <div className="main-column">
        <header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{activeLabel}</strong></div><div className="topbar-actions"><label className="search-field"><Search size={15} /><Input aria-label="Search this preview" placeholder="Search" disabled /><kbd>⌘ K</kbd></label><span className="preview-badge"><span /> Preview mode</span><Button className="mobile-menu" variant="ghost" size="icon" aria-label="Open navigation" onClick={() => setActivePage('overview')}><LayoutDashboard size={18} /></Button></div></header>
        <main className="page-content" key={activePage}>
          <OverviewPageShell active={activePage} onNavigate={setActivePage} knowledgeExplorer={knowledgeExplorer} />
        </main>
      </div>
    </div>
  );
}
