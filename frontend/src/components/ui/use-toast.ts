// Minimal use-toast implementation
import { useState, useEffect } from "react"

const TOAST_LIMIT = 1
const TOAST_REMOVE_DELAY = 1000000

type ToastProps = {
    id: string
    title?: string
    description?: string
    action?: React.ReactNode
    variant?: "default" | "destructive"
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

let count = 0

function genId() {
    count = (count + 1) % Number.MAX_VALUE
    return count.toString()
}

type ActionType = {
    type: "ADD_TOAST" | "UPDATE_TOAST" | "DISMISS_TOAST" | "REMOVE_TOAST"
    toast: Partial<ToastProps>
}

interface State {
    toasts: ToastProps[]
}

const toastTimeouts = new Map<string, ReturnType<typeof setTimeout>>()

const addToRemoveQueue = (toastId: string) => {
    if (toastTimeouts.has(toastId)) {
        return
    }

    const timeout = setTimeout(() => {
        toastTimeouts.delete(toastId)
        dispatch({
            type: "REMOVE_TOAST",
            toast: {
                id: toastId,
            },
        })
    }, TOAST_REMOVE_DELAY)

    toastTimeouts.set(toastId, timeout)
}

export const reducer = (state: State, action: ActionType): State => {
    switch (action.type) {
        case "ADD_TOAST":
            return {
                ...state,
                toasts: [
                    { ...action.toast, id: genId(), open: true } as ToastProps, // simple append
                    ...state.toasts
                ].slice(0, TOAST_LIMIT),
            }
        case "UPDATE_TOAST":
            return {
                ...state,
                toasts: state.toasts.map((t) =>
                    t.id === action.toast.id ? { ...t, ...action.toast } : t
                ),
            }
        case "DISMISS_TOAST": {
            const { id } = action.toast

            // ! Side effects ! - This could be extracted into a subscribe
            if (id) {
                addToRemoveQueue(id)
            } else {
                state.toasts.forEach((toast) => {
                    addToRemoveQueue(toast.id)
                })
            }

            return {
                ...state,
                toasts: state.toasts.map((t) =>
                    t.id === id || action.toast.id === undefined
                        ? {
                            ...t,
                            open: false,
                        }
                        : t
                ),
            }
        }
        case "REMOVE_TOAST":
            if (action.toast.id === undefined) {
                return {
                    ...state,
                    toasts: [],
                }
            }
            return {
                ...state,
                toasts: state.toasts.filter((t) => t.id !== action.toast.id),
            }
    }
}

const listeners: Array<(state: State) => void> = []

let memoryState: State = { toasts: [] }

function dispatch(action: ActionType) {
    memoryState = reducer(memoryState, action)
    listeners.forEach((listener) => {
        listener(memoryState)
    })
}

type Toast = Omit<ToastProps, "id">

function toast({ ...props }: Toast) {
    const id = genId()

    const update = (props: Toast) =>
        dispatch({
            type: "UPDATE_TOAST",
            toast: { ...props, id },
        })
    const dismiss = () => dispatch({ type: "DISMISS_TOAST", toast: { id } })

    dispatch({
        type: "ADD_TOAST",
        toast: {
            ...props,
            id,
            open: true,
            onOpenChange: (open) => {
                if (!open) dismiss()
            },
        },
    })

    return {
        id: id,
        dismiss,
        update,
    }
}

function useToast() {
    const [state, setState] = useState<State>(memoryState)

    useEffect(() => {
        listeners.push(setState)
        return () => {
            const index = listeners.indexOf(setState)
            if (index > -1) {
                listeners.splice(index, 1)
            }
        }
    }, [state])

    return {
        ...state,
        toast,
        dismiss: (toastId?: string) => dispatch({ type: "DISMISS_TOAST", toast: { id: toastId } }),
    }
}

export { useToast, toast }
