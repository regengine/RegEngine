import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { CheckCircle, AlertTriangle, XCircle } from "lucide-react"

interface Control {
    id: string
    name: string
    status: "green" | "yellow" | "red" | "gray"
}

interface PillarCardProps {
    title: string
    status: "green" | "yellow" | "red" | "gray"
    controls: Control[]
}

export function PillarCard({ title, status, controls }: PillarCardProps) {
    const statusColor =
        status === "green" ? "bg-green-500" :
            status === "yellow" ? "bg-yellow-500" :
                status === "red" ? "bg-red-500" : "bg-gray-500"

    const statusIcon =
        status === "green" ? <CheckCircle className="text-green-600 h-6 w-6" /> :
            status === "yellow" ? <AlertTriangle className="text-yellow-600 h-6 w-6" /> :
                status === "red" ? <XCircle className="text-red-600 h-6 w-6" /> :
                    <div className="h-6 w-6 rounded-full border-2 border-gray-300" />

    return (
        <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-lg font-bold">{title}</CardTitle>
                {statusIcon}
            </CardHeader>
            <CardContent>
                <div className="space-y-4 mt-2">
                    {controls.map(control => (
                        <div key={control.id} className="flex justify-between items-center text-sm border-b pb-2 last:border-0 last:pb-0">
                            <span>{control.name}</span>
                            <StatusBadge status={control.status} />
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}

function StatusBadge({ status }: { status: string }) {
    if (status === "green") return <Badge className="bg-green-100 text-green-800 hover:bg-green-200">Safe</Badge>
    if (status === "yellow") return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-200">Review</Badge>
    if (status === "red") return <Badge className="bg-red-100 text-red-800 hover:bg-red-200">Missing</Badge>
    return <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-200">Unknown</Badge>
}
