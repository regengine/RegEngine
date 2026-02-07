"use client"

import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Checkbox } from "@/components/ui/checkbox"

export default function HealthcareSetupPage() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const tenantId = searchParams.get("tenant")

    const [step, setStep] = useState(1)
    const [formData, setFormData] = useState({
        name: "",
        state: "",
        facilityType: "",
        dispensesMedication: false,
        hasPaidStaff: false
    })

    const handleNext = () => setStep(step + 1)
    const handleBack = () => setStep(step - 1)

    const handleSubmit = async () => {
        // In a real app, this would POST to /api/verticals/healthcare/projects
        // For MVP demo, we'll store in localStorage to simulate state persistence
        console.log("Submitting Setup:", formData)

        // Simulate API delay
        await new Promise(resolve => setTimeout(resolve, 500))

        // Redirect to dashboard with a flag to load mock data
        router.push(`/verticals/healthcare/dashboard?tenant=${tenantId}&demo=true&meds=${formData.dispensesMedication}`)
    }

    return (
        <div className="flex items-center justify-center min-h-screen bg-slate-50 p-4">
            <Card className="w-full max-w-lg">
                <CardHeader>
                    <CardTitle>Clinic Safety Setup</CardTitle>
                    <CardDescription>Step {step} of 3: {
                        step === 1 ? "Organization Details" :
                            step === 2 ? "Operational Model" :
                                "Review & Finish"
                    }</CardDescription>
                </CardHeader>
                <CardContent>
                    {step === 1 && (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="name">Clinic Name</Label>
                                <Input
                                    id="name"
                                    placeholder="e.g. Hope Free Clinic"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="state">State</Label>
                                <Select onValueChange={(val) => setFormData({ ...formData, state: val })}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select State" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="CA">California</SelectItem>
                                        <SelectItem value="TX">Texas</SelectItem>
                                        <SelectItem value="FL">Florida</SelectItem>
                                        <SelectItem value="NY">New York</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="type">Facility Type</Label>
                                <Select onValueChange={(val) => setFormData({ ...formData, facilityType: val })}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Facility Type" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="free_clinic">Free Clinic</SelectItem>
                                        <SelectItem value="charitable_clinic">Charitable Clinic</SelectItem>
                                        <SelectItem value="fqhc_lookalike">FQHC Look-Alike</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-6">
                            <div className="flex items-center justify-between space-x-2">
                                <div className="space-y-0.5">
                                    <Label className="text-base">Dispense Medication?</Label>
                                    <p className="text-sm text-gray-500">
                                        Does your clinic dispense prescription drugs on-site?
                                    </p>
                                </div>
                                <Switch
                                    checked={formData.dispensesMedication}
                                    onCheckedChange={(checked) => setFormData({ ...formData, dispensesMedication: checked })}
                                />
                            </div>
                            <div className="flex items-center justify-between space-x-2">
                                <div className="space-y-0.5">
                                    <Label className="text-base">Paid Staff?</Label>
                                    <p className="text-sm text-gray-500">
                                        Do you have any W-2 employees?
                                    </p>
                                </div>
                                <Switch
                                    checked={formData.hasPaidStaff}
                                    onCheckedChange={(checked) => setFormData({ ...formData, hasPaidStaff: checked })}
                                />
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-4">
                            <div className="bg-slate-100 p-4 rounded-md space-y-2">
                                <p><strong>Name:</strong> {formData.name}</p>
                                <p><strong>State:</strong> {formData.state}</p>
                                <p><strong>Type:</strong> {formData.facilityType?.replace("_", " ")}</p>
                                <p><strong>Dispensing:</strong> {formData.dispensesMedication ? "Yes" : "No"}</p>
                            </div>
                            <p className="text-sm text-slate-500">
                                By clicking Finish, you acknowledge that MSCF provides operational tools, not legal advice.
                            </p>
                        </div>
                    )}
                </CardContent>
                <CardFooter className="flex justify-between">
                    {step > 1 ? (
                        <Button variant="outline" onClick={handleBack}>Back</Button>
                    ) : (
                        <div />
                    )}

                    {step < 3 ? (
                        <Button onClick={handleNext}>Next</Button>
                    ) : (
                        <Button onClick={handleSubmit}>Finish & Create Clinic</Button>
                    )}
                </CardFooter>
            </Card>
        </div>
    )
}
