import { useState, type ReactElement } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ErrorNotice, InfoNotice } from '@/components/common/Feedback';
import { TextAreaField } from '@/components/forms/Field';
import { Modal } from '@/components/dialogs/Modal';
import type { RosterImportResult } from '../../../api/accounts';
import { useImportRosterCsv, useImportRosterSheet } from '../hooks';

interface ImportRosterDialogProps {
  open: boolean;
  onClose: () => void;
}

const describe = (result: RosterImportResult): string =>
  `${result.rows} row${result.rows === 1 ? '' : 's'} read: ${result.created} added, ${result.updated} updated, ${result.removed} removed, ${result.skipped.length} skipped`;

/**
 * Two ways in: the Google Sheet the server is configured with, or a CSV the
 * operator pastes. Both go through the same header-label mapping, so a
 * column can move without anything breaking.
 */
export const ImportRosterDialog = ({ open, onClose }: ImportRosterDialogProps): ReactElement => {
  const [csv, setCsv] = useState('');
  const [result, setResult] = useState<RosterImportResult | null>(null);

  const fromSheet = useImportRosterSheet();
  const fromCsv = useImportRosterCsv();
  const pending = fromSheet.isPending || fromCsv.isPending;
  const failure = fromSheet.error ?? fromCsv.error;

  const finish = (imported: RosterImportResult): void => {
    setResult(imported);
    toast.success(describe(imported));
  };

  return (
    <Modal
      open={open}
      title="Import the roster"
      description="Columns are matched by their header — FACEBOOK NAME, USERNAME, PASSWORD, GMAIL, PASS FOR GMAIL, NUMBER, PROXY. Only rows with both a username and a password count. The row number in column A is the key; a known number is updated, a new one becomes an account, and a roster account whose row stops counting is removed."
      onClose={onClose}
      size="wide"
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      <Tabs defaultValue="sheet">
        <TabsList>
          <TabsTrigger value="sheet">Google Sheet</TabsTrigger>
          <TabsTrigger value="csv">Paste CSV</TabsTrigger>
        </TabsList>

        <TabsContent value="sheet" className="grid gap-4 pt-2">
          <InfoNotice>
            Reads the sheet set in the server's SHEETS_SHEET_ID. A sheet shared with "anyone with
            the link" needs nothing else; a private sheet needs the service-account key at
            SHEETS_SERVICE_ACCOUNT and must be shared with that account.
          </InfoNotice>
          <div>
            <Button
              disabled={pending}
              onClick={() => fromSheet.mutate(undefined, { onSuccess: finish })}
            >
              Import from the sheet
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="csv" className="grid gap-4 pt-2">
          <TextAreaField
            label="CSV"
            value={csv}
            placeholder={
              'NO,FACEBOOK NAME,USERNAME,PASSWORD,GMAIL,PASS FOR GMAIL,NUMBER\n1,Maria Santos,maria@example.com,secret,maria@gmail.com,secret,09171234567'
            }
            onChange={(event) => setCsv(event.target.value)}
          />
          <div>
            <Button
              disabled={pending || csv.trim() === ''}
              onClick={() => fromCsv.mutate(csv, { onSuccess: finish })}
            >
              Import the pasted rows
            </Button>
          </div>
        </TabsContent>
      </Tabs>

      {failure !== null && <ErrorNotice error={failure} />}

      {result !== null && (
        <div className="grid gap-2 rounded-md border bg-muted/40 p-3 text-sm">
          <p>{describe(result)}</p>
          {result.skipped.length > 0 && (
            <ul className="grid gap-1 text-xs text-muted-foreground">
              {result.skipped.slice(0, 20).map((entry) => (
                <li key={entry.name}>
                  <span className="font-mono">{entry.name}</span>: {entry.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
};
