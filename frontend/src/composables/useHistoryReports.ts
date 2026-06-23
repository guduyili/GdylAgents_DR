import { ref } from "vue";
import { getReport, listReports, type ReportDetail, type ReportItem } from "../services/api";

export function useHistoryReports() {
  const historyReports = ref<ReportItem[]>([]);
  const historyLoading = ref(false);
  const selectedReport = ref<ReportDetail | null>(null);
  const historyPageOpen = ref(false);

  async function loadHistory() {
    if (historyLoading.value) {
      return;
    }
    historyLoading.value = true;
    try {
      historyReports.value = await listReports();
    } catch {
      // 服务不可用时静默失败
    } finally {
      historyLoading.value = false;
    }
  }

  function openHistoryPage() {
    historyPageOpen.value = true;
    selectedReport.value = null;
    void loadHistory();
  }

  function closeHistoryPage() {
    historyPageOpen.value = false;
  }

  async function openReport(noteId: string) {
    try {
      selectedReport.value = await getReport(noteId);
    } catch (error) {
      console.error("加载报告失败", error);
    }
  }

  return {
    historyReports,
    historyLoading,
    selectedReport,
    historyPageOpen,
    loadHistory,
    openHistoryPage,
    closeHistoryPage,
    openReport
  };
}