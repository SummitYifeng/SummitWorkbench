import './style.css';
import { initializeTheme } from './theme';

import { mountLegacyWorkbench } from './legacy-main';

// Composition root：统一启动旧版 feature bundle；新 feature 只从这里组合。
initializeTheme();
mountLegacyWorkbench();
