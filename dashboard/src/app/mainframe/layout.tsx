import { PageShell } from '@/components/PageShell';
import { MainframeNav } from '@/components/MainframeNav';

export default function MainframeLayout({ children }: { children: React.ReactNode }) {
  return (
    <PageShell title="Mainframe Control Center"
      subtitle="Every action here runs on IBM z/OS through Zowe: the backend calls Zowe CLI, which talks to z/OSMF.">
      <MainframeNav />
      {children}
    </PageShell>
  );
}
