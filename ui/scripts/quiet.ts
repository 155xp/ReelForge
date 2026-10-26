// Imported first by anything that draws the window without a terminal: React then doesn't expect test-library act()
// wrappers round every update.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false
export {}
