import { useEffect, useState } from 'react'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'

// Register Chart.js components
ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend
)

// Types for API responses
interface ScoreBucket {
    bucket: string
    count: number
}

interface PassRate {
    task: string
    avg_score: number
    attempts: number
}

interface TimelineEntry {
    date: string
    submissions: number
}

interface GroupStat {
    group: string
    avg_score: number
    students: number
}

const API_BASE = import.meta.env.VITE_API_TARGET || 'http://localhost:42001'

export default function Dashboard() {
    const [lab, setLab] = useState('lab-04')
    const [scores, setScores] = useState<ScoreBucket[]>([])
    const [timeline, setTimeline] = useState<TimelineEntry[]>([])
    const [passRates, setPassRates] = useState<PassRate[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchAnalytics = async () => {
        setLoading(true)
        setError(null)
        const apiKey = localStorage.getItem('api_key')

        if (!apiKey) {
            setError('API key not found. Please login first.')
            setLoading(false)
            return
        }

        const headers = {
            'Authorization': `Bearer ${apiKey}`,
            'Accept': 'application/json',
        }

        try {
            const [scoresRes, timelineRes, passRatesRes] = await Promise.all([
                fetch(`${API_BASE}/analytics/scores?lab=${lab}`, { headers }),
                fetch(`${API_BASE}/analytics/timeline?lab=${lab}`, { headers }),
                fetch(`${API_BASE}/analytics/pass-rates?lab=${lab}`, { headers }),
            ])

            if (!scoresRes.ok || !timelineRes.ok || !passRatesRes.ok) {
                throw new Error('Failed to fetch analytics data')
            }

            const [scoresData, timelineData, passRatesData] = await Promise.all([
                scoresRes.json(),
                timelineRes.json(),
                passRatesRes.json(),
            ])

            setScores(scoresData)
            setTimeline(timelineData)
            setPassRates(passRatesData)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchAnalytics()
    }, [lab])

    // Chart data for scores histogram
    const scoresChartData = {
        labels: scores.map((s: ScoreBucket) => s.bucket),
        datasets: [
            {
                label: 'Number of submissions',
                data: scores.map((s: ScoreBucket) => s.count),
                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1,
            },
        ],
    }

    // Chart data for timeline
    const timelineChartData = {
        labels: timeline.map((t: TimelineEntry) => t.date),
        datasets: [
            {
                label: 'Submissions',
                data: timeline.map((t: TimelineEntry) => t.submissions),
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.1)',
                tension: 0.1,
            },
        ],
    }

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: { position: 'top' as const },
            title: { display: true, text: 'Analytics Dashboard' },
        },
    }

    if (loading) return <div className="p-4">Loading analytics...</div>
    if (error) return <div className="p-4 text-red-500">Error: {error}</div>

    return (
        <div className="p-4 space-y-6">
            <div className="flex items-center gap-4">
                <label className="font-medium">Select Lab:</label>
                <select
                    value={lab}
                    onChange={(e) => setLab(e.target.value)}
                    className="border rounded px-3 py-1"
                >
                    <option value="lab-01">Lab 01</option>
                    <option value="lab-02">Lab 02</option>
                    <option value="lab-03">Lab 03</option>
                    <option value="lab-04">Lab 04</option>
                </select>
                <button
                    onClick={fetchAnalytics}
                    className="bg-blue-500 text-white px-4 py-1 rounded hover:bg-blue-600"
                >
                    Refresh
                </button>
            </div>

            {/* Scores Histogram */}
            <div className="border rounded p-4">
                <h3 className="text-lg font-semibold mb-4">Score Distribution</h3>
                <Bar data={scoresChartData} options={chartOptions} />
            </div>

            {/* Timeline Chart */}
            <div className="border rounded p-4">
                <h3 className="text-lg font-semibold mb-4">Submissions Timeline</h3>
                <Line data={timelineChartData} options={chartOptions} />
            </div>

            {/* Pass Rates Table */}
            <div className="border rounded p-4">
                <h3 className="text-lg font-semibold mb-4">Pass Rates by Task</h3>
                <table className="w-full">
                    <thead>
                        <tr className="border-b">
                            <th className="text-left py-2">Task</th>
                            <th className="text-right py-2">Avg Score</th>
                            <th className="text-right py-2">Attempts</th>
                        </tr>
                    </thead>
                    <tbody>
                        {passRates.map((pr: PassRate) => (
                            <tr key={pr.task} className="border-b">
                                <td className="py-2">{pr.task}</td>
                                <td className="text-right py-2">{pr.avg_score}%</td>
                                <td className="text-right py-2">{pr.attempts}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}