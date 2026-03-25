import { useCallback } from 'react';
import type { ProgramSummaryData } from '../../types/index.ts';

interface ProgramSummaryProps {
  data: ProgramSummaryData;
  onChange: (data: ProgramSummaryData) => void;
}

export function ProgramSummary({ data, onChange }: ProgramSummaryProps) {
  const update = useCallback(
    <K extends keyof ProgramSummaryData>(field: K, value: ProgramSummaryData[K]) => {
      onChange({ ...data, [field]: value });
    },
    [data, onChange]
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-1">Program Summary</h3>
        <p className="text-sm text-gray-600 mb-6">
          Provide an overview of the organization, location, and project details.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Organization Name</label>
          <input
            type="text"
            value={data.organizationName}
            onChange={e => update('organizationName', e.target.value)}
            placeholder="e.g., Jan Swasthya Sahyog"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
          <input
            type="text"
            value={data.location}
            onChange={e => update('location', e.target.value)}
            placeholder="e.g., Bilaspur, Chhattisgarh"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Location Hierarchy</label>
          <input
            type="text"
            value={data.locationHierarchy}
            onChange={e => update('locationHierarchy', e.target.value)}
            placeholder="e.g., State > District > Block > Village"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Previous Data System</label>
          <input
            type="text"
            value={data.previousSystem}
            onChange={e => update('previousSystem', e.target.value)}
            placeholder="e.g., Paper-based registers, Excel"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Challenges with Current System</label>
          <textarea
            value={data.challenges}
            onChange={e => update('challenges', e.target.value)}
            placeholder="Describe the key challenges that Avni is expected to address..."
            rows={3}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Program Start Date</label>
          <input
            type="date"
            value={data.programStartDate}
            onChange={e => update('programStartDate', e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Avni Rollout Date</label>
          <input
            type="date"
            value={data.rolloutDate}
            onChange={e => update('rolloutDate', e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Number of Users</label>
          <input
            type="number"
            value={data.numberOfUsers || ''}
            onChange={e => update('numberOfUsers', parseInt(e.target.value) || 0)}
            placeholder="0"
            min="0"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Data Migration Required</label>
          <button
            type="button"
            onClick={() => update('dataMigration', !data.dataMigration)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 ${
              data.dataMigration ? 'bg-teal-600' : 'bg-gray-200'
            }`}
            role="switch"
            aria-checked={data.dataMigration}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                data.dataMigration ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
          <span className="ml-3 text-sm text-gray-600">{data.dataMigration ? 'Yes' : 'No'}</span>
        </div>
      </div>
    </div>
  );
}
