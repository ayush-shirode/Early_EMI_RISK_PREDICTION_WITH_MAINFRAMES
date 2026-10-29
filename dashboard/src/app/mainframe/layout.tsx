import { PageShell } from '@/components/PageShell';
import { MainframeNav } from '@/components/MainframeNav';

export default function MainframeLayout({ children }: { children: React.ReactNode }) {
  return (
    <PageShell title="Mainframe Control Center"
      subtitle="Every action here runs on IBM z/OS: the backend calls the z/OSMF REST API directly over HTTPS.">
      <MainframeNav />
      {children}
    </PageShell>
  );
}
