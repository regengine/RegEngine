'use client'

import { useEffect } from 'react'
import { defineCustomElements } from '@ionic/pwa-elements/loader'

export function PWAElements() {
    useEffect(() => {
        defineCustomElements(window)
    }, [])

    return null
}
