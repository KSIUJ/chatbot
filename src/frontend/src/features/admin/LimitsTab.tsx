import { useState } from 'react';
import type { Translation } from '../preferences/languages';
import { fetchSettings, type AdminSettings } from './adminApi';
import { LoadError, LoadingRow } from './AdminCommon';
import ChatSwitch from './ChatSwitch';
import GlobalLimitsForm from './GlobalLimitsForm';
import { useLoader } from './useLoader';
import UserLimits from './UserLimits';

interface LimitsTabProps {
  lang: Translation;
}

// Chat kill switch, global limits form and the user list with per-person exceptions.
export default function LimitsTab({ lang }: LimitsTabProps) {
  const text = lang.admin;
  const loaded = useLoader(fetchSettings);
  // the last saved settings win over the loaded ones
  const [saved, setSaved] = useState<AdminSettings | null>(null);
  const settings = saved ?? loaded.data;

  if (settings === null) {
    return loaded.hasError ? (
      <LoadError text={text} retryLabel={lang.retry} onRetry={loaded.reload} />
    ) : (
      <LoadingRow label={lang.loading} />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ChatSwitch lang={lang} settings={settings} onSaved={setSaved} />
      <GlobalLimitsForm text={text} settings={settings} onSaved={setSaved} />
      {/* remounted when the global limit changes: effective limits are reloaded */}
      <UserLimits
        key={settings.dailyQuestionLimit}
        lang={lang}
        globalLimit={settings.dailyQuestionLimit}
        range={settings.ranges.userDailyLimit}
      />
    </div>
  );
}
